# MacroDroid 설정

이 문서는 공폰의 카카오톡 알림 한 건을 숲봇 서버에 보내고, 받은 텍스트를 같은 알림에 답장하는 매크로를 직접 만드는 순서입니다. 검증되지 않은 `.macro` 가져오기 파일은 제공하지 않습니다. 화면의 항목 이름은 MacroDroid 버전과 기기 언어에 따라 조금 다를 수 있습니다.

MacroDroid 공식 설명도 함께 확인할 수 있습니다.

- [Notification Trigger](https://www.macrodroidforum.com/wiki/index.php?title=Trigger%3A_Notification)
- [HTTP Request](https://macrodroidforum.com/wiki/index.php/Action%3A_HTTP_Request)
- [Notification Reply](https://www.macrodroidforum.com/wiki/index.php?title=Action%3A_Notification_Reply)

## 0. 시작 전 확인

- 공폰에서 카카오톡 봇 계정이 대상 단톡방에 들어가 있어야 합니다.
- MacroDroid에 **알림 접근 권한**을 허용하고, 제조사 배터리 절전 대상에서 제외합니다.
- Vercel 배포 주소와 배포 때 정한 `SOOPBOT_TOKEN`을 준비합니다.
- 브라우저에서 `https://<project>.vercel.app/api/reply`를 열었을 때 `ok`가 보여야 합니다.

## 1. 새 매크로와 트리거 만들기

1. MacroDroid에서 새 매크로를 만들고 이름을 `숲봇`으로 정합니다.
2. 트리거로 **Notification Received**(알림 수신)를 선택합니다.
3. 애플리케이션은 **카카오톡만** 선택합니다.
4. 알림 제목/대화방 조건은 대상 방의 제목과 **완전히 같게** 설정합니다. 예: `우리 동네 AI 숲`.
5. 알림 내용 조건은 **포함(Contains)** `숲봇아`로 설정합니다.
6. 봇 계정이 보낸 알림은 제외합니다. 발신자 조건을 지원하는 화면에서는 봇의 정확한 카카오톡 이름을 **제외(Excludes)**에 넣으세요. 기기에서 발신자와 본문이 합쳐져 보인다면 실제 자기 답변 알림 형식에 맞춰 같은 제외 조건을 추가합니다.

마지막 제외 조건은 답변이 다시 매크로를 실행하는 재귀를 막기 위한 필수 안전장치입니다. 처음에는 테스트 방 한 곳만 지정하세요.

## 2. 응답 변수 초기화하기

HTTP 요청보다 앞에 다음 두 동작을 이 순서로 추가합니다.

1. 문자열 변수 `soopbot_reply`를 만들고 **빈 문자열로 설정/초기화**합니다.
2. 정수 변수 `soopbot_status`를 만들고 **`0`으로 설정**합니다.

두 변수는 매 요청 전에 반드시 초기화해야 합니다. 이전 요청의 답이나 상태 코드가 남으면 실패한 요청 뒤에 예전 답장을 보낼 수 있습니다.

## 3. HTTP Request 동작 추가하기

**HTTP Request** 동작에 다음 값을 그대로 맞춥니다.

| 항목 | 값 |
| --- | --- |
| Method | `POST` |
| URL | `https://<project>.vercel.app/api/reply?room=room1` |
| Content Body | 알림 본문 매직 텍스트 `{notification}` |
| Content Type | Custom: `text/plain; charset=utf-8` |
| Header 이름 | `X-Bot-Token` |
| Header 값 | Vercel의 `SOOPBOT_TOKEN`과 동일한 24자 이상 토큰 |
| Timeout | `60`초 |
| 응답 본문 저장 | 문자열 변수 `soopbot_reply` |
| HTTP 반환 코드 저장 | 정수 변수 `soopbot_status` |
| 실행 방식 | **Block next action until complete** 활성화 |

토큰 값에는 따옴표를 붙이지 마세요. URL의 `<project>`는 실제 Vercel 프로젝트 도메인으로 바꿉니다. Vercel의 `SOOPBOT_ROOM_KEY`를 바꾼 경우에는 `room=room1`도 같은 값으로 바꿔야 합니다.

**Block next action until complete**를 켜지 않으면 HTTP 요청이 끝나기 전에 다음 조건이 실행되어 상태가 `0`인 채로 남을 수 있습니다.

## 4. 성공했을 때만 알림 답장하기

1. **If 절**을 추가합니다.
2. 첫 조건은 정수 변수 `soopbot_status == 200`입니다.
3. AND 조건으로 문자열 변수 `soopbot_reply`가 비어 있지 않음을 추가합니다.
4. If 안에 **Notification Reply** 동작을 넣습니다.
5. 알림 선택은 **Use Notification Trigger**를 사용해 이 매크로를 시작한 카카오톡 알림을 가리킵니다.
6. 답장 텍스트는 `[v=soopbot_reply]`로 지정합니다.
7. 실패를 알림으로 다시 보내는 Else 동작은 만들지 않습니다. 상태 확인은 MacroDroid 시스템 로그에서 합니다.

최종 순서는 다음과 같아야 합니다.

```text
Notification Received: 카카오톡 + 정확한 방 제목 + 본문에 숲봇아 + 봇 발신자 제외
  → soopbot_reply = ""
  → soopbot_status = 0
  → HTTP Request (완료될 때까지 다음 동작 차단)
  → If soopbot_status == 200 AND soopbot_reply is not empty
      → Notification Reply: [v=soopbot_reply]
```

## 5. 테스트하기

1. 매크로를 저장하고 활성화합니다.
2. 다른 계정으로 정확한 대상 방에 `숲봇아 안녕`을 보냅니다.
3. `soopbot_status`가 `200`, `soopbot_reply`가 비어 있지 않은지 MacroDroid 로그에서 확인합니다.
4. 답장이 한 번만 오는지 확인합니다.
5. 호출어 없이 `안녕`만 보내거나 다른 방에서 호출했을 때는 답장하지 않는지 확인합니다.
6. 봇 계정의 답장 알림이 다시 트리거되지 않는지 확인합니다. 재실행된다면 1단계의 봇 발신자 제외 조건을 실제 알림 형식에 맞게 보강한 뒤 다시 테스트합니다.

막히면 [문제 해결](troubleshooting.md)을 확인하세요. 호출어와 방 키를 바꾸려면 [맞춤 설정](customize.md)을 먼저 읽으세요.
