import asyncio
import json
import websockets

VTS_URL = "ws://localhost:8001"  # VTSのAPIポート（設定で確認してね）

PLUGIN_NAME = "SilenceFadeSystem"
PLUGIN_DEVELOPER = "Shiho"


async def get_token():
    async with websockets.connect(VTS_URL) as ws:
        # ① トークンくださいリクエスト（AuthenticationTokenRequest）
        request = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "get-token",
            "messageType": "AuthenticationTokenRequest",
            "data": {
                "pluginName": PLUGIN_NAME,
                "pluginDeveloper": PLUGIN_DEVELOPER,
                "pluginIcon": "",
                "pluginWebsite": ""
            }
        }

        await ws.send(json.dumps(request))
        print("トークンリクエストを送信しました。VTS側で許可ポップアップが出るはず！")

        # ② VTSからの返信を待つ
        response_raw = await ws.recv()
        response = json.loads(response_raw)
        print("VTSからの返信:", response)

        token = response.get("data", {}).get("authenticationToken")
        if token:
            print("\n===== 取得したトークン =====")
            print(token)
            print("===========================")
        else:
            print("\nトークンが取得できませんでした。VTS側で拒否されたかも？")


if __name__ == "__main__":
    asyncio.run(get_token())