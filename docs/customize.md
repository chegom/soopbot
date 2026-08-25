# 숲봇 맞춤 설정

기본값만으로 먼저 답장에 성공한 뒤 하나씩 바꾸는 것을 권합니다. Vercel 환경변수를 수정하면 새 값이 실행 코드에 적용되도록 프로젝트를 다시 배포하세요.

## 호출어를 `숲봇아`에서 `나무야`로 바꾸기

호출어는 서버와 공폰 양쪽이 같아야 합니다.

1. Vercel 프로젝트의 **Settings → Environment Variables**에서 `SOOPBOT_TRIGGER` 값을 `나무야`로 추가하거나 변경합니다.
2. 변경한 환경변수를 적용해 **Redeploy**합니다.
3. MacroDroid의 숲봇 매크로를 열고 Notification Received 트리거의 **내용 포함** 값을 `숲봇아`에서 `나무야`로 바꿉니다.
4. 매크로를 저장한 뒤 대상 방에서 `나무야 안녕`을 보냅니다.
5. `숲봇아 안녕`에는 답하지 않고 `나무야 안녕`에는 한 번 답하는지 확인합니다.

Vercel만 바꾸면 MacroDroid가 요청을 보내지 않고, MacroDroid만 바꾸면 서버가 호출어를 찾지 못해 답장 본문 없이 `204`를 반환합니다.

## 말투와 역할 바꾸기

`SOOPBOT_PERSONA`에 봇의 역할과 답변 원칙을 짧고 분명하게 적습니다.

```text
초보자에게 어려운 말을 풀어 쓰고, 핵심을 세 문단 안에 답하는 독서모임 도우미로 답하세요.
```

이 값은 최대 1,000자입니다. 비밀값이나 다른 사람의 개인정보는 넣지 마세요. 숲봇은 사용자의 질문을 지침이 아닌 입력으로 구분해 보내지만, 모델 답변은 중요한 의사결정 전에 사용자가 다시 확인해야 합니다.

## 방 키 바꾸기

기본 방 키는 `room1`입니다. 이 값은 카카오톡 방 제목이 아니라 서버 URL에 쓰는 별도 키입니다.

1. Vercel의 `SOOPBOT_ROOM_KEY`를 원하는 값으로 바꾸고 다시 배포합니다.
2. MacroDroid HTTP URL의 쿼리를 같은 값으로 바꿉니다. 예: `SOOPBOT_ROOM_KEY=bookclub`이면 `/api/reply?room=bookclub`.

서로 다르면 서버는 의도적으로 본문 없는 `204`를 반환합니다. 방 제목 제한은 MacroDroid Notification Received 트리거에서 별도로 유지하세요.

## 모델과 답변 한도 바꾸기

| 환경변수 | 기본값 | 허용 범위/용도 |
| --- | --- | --- |
| `OPENAI_MODEL` | `gpt-5.6-luna` | 본인 OpenAI API 계정에서 사용할 수 있는 모델 이름 |
| `SOOPBOT_MAX_OUTPUT_CHARS` | `1000` | 카카오톡으로 돌려줄 최대 문자 수, 100~4,000 |
| `SOOPBOT_MAX_OUTPUT_TOKENS` | `500` | OpenAI가 생성할 최대 출력 토큰, 1~4,000 |
| `SOOPBOT_TIMEOUT_SECONDS` | `40` | OpenAI 요청 제한 시간, 1~120초 |
| `SOOPBOT_REQUESTS_PER_MINUTE` | `10` | 한 방의 분당 요청 한도, 1~120 |

MacroDroid HTTP 제한 시간은 기본 안내대로 60초를 유지하세요. 서버의 `SOOPBOT_TIMEOUT_SECONDS`를 60초보다 길게 잡으면 공폰이 먼저 기다리기를 끝낼 수 있습니다.

변경 뒤에는 `숲봇아 짧게 자기소개해 줘`처럼 비용이 작은 질문으로 한 번 확인하고, 문제가 있으면 [문제 해결](troubleshooting.md)을 참고하세요.
