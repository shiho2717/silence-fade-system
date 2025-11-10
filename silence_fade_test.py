import time
import json
import asyncio

import numpy as np
import sounddevice as sd
import websockets

# ==========================
# 設定パラメータ（サイレンス検知＆フェード）
# ==========================

CHECK_INTERVAL = 0.1        # 何秒ごとに音量を測るか
SAMPLE_RATE = 16000         # 1秒あたりのサンプル数
SILENCE_THRESHOLD_DB = -55.0  # これより小さければ「無言」とみなす

FADE_START_TIME = 10.0      # 無言が何秒続いたらフェードアウト開始か
FADE_SPEED_OUT = 0.007      # フェードアウトの速さ（小さいほどゆっくり）

FADE_IN_SPEED = 0.6         # フェードインの速さ（大きいほどボワッと速く）

MIN_EYE_GLOW = 0.0          # 目の光の下限
MAX_EYE_GLOW = 1.0          # 目の光の上限


# ==========================
# VTS 接続設定
# ==========================

VTS_HOST = "localhost"      # VTSを動かしているPC。基本同じPCなら localhost
VTS_PORT = 8001             # VTSのAPI設定画面で確認したポート番号

VTS_URL = f"ws://{VTS_HOST}:{VTS_PORT}"

VTS_API_NAME = "VTubeStudioPublicAPI"
VTS_API_VERSION = "1.0"

PLUGIN_NAME = "SilenceFadeSystem"
PLUGIN_DEVELOPER = "Shiho"

# ★ここに VTS の API タブで発行した Authentication Token を貼る★
VTS_AUTH_TOKEN = "PUT_YOUR_TOKEN_HERE"

# VTS が起動してないときに毎フレームエラー出さないためのフラグ
_vts_error_logged = False


# ==========================
# 音量を測る関数
# ==========================

def measure_volume_db(duration: float, samplerate: int = SAMPLE_RATE) -> float:
    """
    duration秒ぶんのマイク入力を録音して、
    「dBっぽい音量」の数値を返す関数。
    値が大きいほど音が大きく、無音に近いほどマイナス方向に大きくなる。
    """

    num_frames = int(duration * samplerate)

    recording = sd.rec(
        frames=num_frames,
        samplerate=samplerate,
        channels=1,
        dtype="float32"
    )
    sd.wait()

    data = np.squeeze(recording)

    rms = np.sqrt(np.mean(data ** 2))
    volume_db = 20 * np.log10(rms + 1e-8)

    return volume_db


# ==========================
# VTS に Param_EyeGlow を送る（非同期）
# ==========================

async def _vts_send_eye_glow_async(eye_glow: float) -> None:
    """
    VTS に接続して認証し、Param_EyeGlow に値を送る。
    毎回 connect してるのでプロトタイプ用のシンプル版。
    """

    async with websockets.connect(VTS_URL) as ws:
        # ① 認証リクエスト
        auth_request = {
            "apiName": VTS_API_NAME,
            "apiVersion": VTS_API_VERSION,
            "requestID": "auth-request",
            "messageType": "AuthenticationRequest",
            "data": {
                "pluginName": PLUGIN_NAME,
                "pluginDeveloper": PLUGIN_DEVELOPER,
                "authenticationToken": VTS_AUTH_TOKEN,
            }
        }
        await ws.send(json.dumps(auth_request))
        auth_response_raw = await ws.recv()
        auth_response = json.loads(auth_response_raw)

        # 認証失敗ならここで終了
        if not auth_response.get("data", {}).get("authenticated", False):
            raise RuntimeError("VTS authentication failed. Token is wrong or plugin not allowed.")

        # ② パラメータ変更リクエスト
        param_request = {
            "apiName": VTS_API_NAME,
            "apiVersion": VTS_API_VERSION,
            "requestID": "set-eye-glow",
            "messageType": "ParameterValueRequest",
            "data": {
                "parameterValues": [
                    {
                        "id": "Param_EyeGlow",  # VTS側のパラメータ名
                        "value": float(eye_glow)
                    }
                ]
            }
        }
        await ws.send(json.dumps(param_request))
        # 応答を確認したければここで recv してもOK
        # _ = await ws.recv()


def send_eye_glow_to_vts(eye_glow: float) -> None:
    """
    メインループから呼ばれる同期関数。
    中で非同期処理を一回動かして VTS に値を送る。
    """
    global _vts_error_logged

    # デバッグとしてターミナルにも出しておく（邪魔なら消してOK）
    print(f"[VTS] eye_glow = {eye_glow:.2f}", end="  \r")

    # トークン未設定なら何もしない
    if VTS_AUTH_TOKEN == "PUT_YOUR_TOKEN_HERE":
        return

    try:
        asyncio.run(_vts_send_eye_glow_async(eye_glow))
    except Exception as e:
        # VTSが起動してない / ポート違う / 認証エラーなど
        if not _vts_error_logged:
            print(f"\n[VTS] 送信エラー: {e}")
            print("VTSが起動しているか、APIポートとトークンを確認してね。")
            _vts_error_logged = True
        # 以降は黙って無視（配信側が落ちないように）


# ==========================
# メインループ
# ==========================

def main():
    silence_duration = 0.0
    eye_glow = MAX_EYE_GLOW
    was_silent = False

    print("Silence Fade System テスト開始")
    print("しゃべったり黙ったりして挙動を確認してみてね。")
    print("Ctrl + C で終了できます。\n")

    try:
        while True:
            # ① 音量測定
            volume_db = measure_volume_db(CHECK_INTERVAL)

            # ② 無言判定
            is_silent = volume_db < SILENCE_THRESHOLD_DB

            # ③ 無言時間 & フェード制御
            if is_silent:
                silence_duration += CHECK_INTERVAL

                if silence_duration >= FADE_START_TIME:
                    eye_glow -= FADE_SPEED_OUT
                    if eye_glow < MIN_EYE_GLOW:
                        eye_glow = MIN_EYE_GLOW

            else:
                # 声が出た瞬間、かつ光が落ちていたときだけ
                # 一旦暗くしてからボワッとフェードイン
                if was_silent and eye_glow < MAX_EYE_GLOW * 0.9:
                    eye_glow = MIN_EYE_GLOW

                silence_duration = 0.0

                eye_glow += FADE_IN_SPEED
                if eye_glow > MAX_EYE_GLOW:
                    eye_glow = MAX_EYE_GLOW

            # ④ 状態表示
            print(
                f"volume={volume_db:6.1f} dB  "
                f"silent_for={silence_duration:5.1f} s  "
                f"eye_glow={eye_glow:4.2f}",
                end="\r",
                flush=True
            )

            # ⑤ VTSに送信
            send_eye_glow_to_vts(eye_glow)

            # ⑥ ちょっと休憩
            time.sleep(0.01)

            # ⑦ 前回の状態を保存
            was_silent = is_silent

    except KeyboardInterrupt:
        print("\n終了します。おつかれさま！")


if __name__ == "__main__":
    main()
