# 숲봇 (Soopbot)

공폰의 카카오톡 알림을 MacroDroid가 받아 Vercel의 개인 서버로 보내고, OpenAI가 만든 답변을 알림 답장으로 돌려주는 공개 템플릿입니다. 기본 호출어는 `숲봇아`이며, 같은 방의 최근 대화 몇 턴을 참고해 답합니다.

> [!IMPORTANT]
> - **ChatGPT Plus·Pro 같은 구독료에는 OpenAI API 사용료가 포함되지 않습니다.**
> - 배포한 사람이 자신의 OpenAI API 사용료를 직접 부담합니다.
> - 이 저장소와 저장소 운영자는 사용자의 API 키를 받거나 저장하지 않습니다. 키는 사용자가 자신의 Vercel 프로젝트 환경변수에 직접 입력합니다.
> - 숲봇용 **전용 OpenAI 프로젝트와 API 키**를 만들고, 프로젝트의 **usage/spend limits와 알림**을 설정하세요. 계정과 모델에는 [모델별 rate limit](https://help.openai.com/en/articles/9186755)도 적용됩니다.

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/clone?repository-url=https%3A%2F%2Fgithub.com%2Fchegom%2Fsoopbot&env=OPENAI_API_KEY%2CSOOPBOT_TOKEN&envDescription=OpenAI%20API%20키와%2024자%20이상의%20숲봇%20전용%20토큰이%20필요합니다.&project-name=soopbot&repository-name=soopbot)

## 준비물

- 카카오톡을 계속 실행할 안드로이드 공폰과 봇용 카카오톡 계정
- 공폰에 설치한 MacroDroid와 알림 접근 권한
- 본인의 GitHub, Vercel, OpenAI API 계정
- OpenAI API 결제 수단 또는 사용 가능한 API 크레딧

이 프로젝트는 카카오, MacroDroid, OpenAI의 공식 제품이 아닙니다. 카카오톡과 안드로이드 업데이트에 따라 알림 답장 동작이 달라질 수 있습니다.

## 10분 설치 순서

1. [OpenAI API 키](https://platform.openai.com/api-keys)를 본인 계정에서 새로 만듭니다.
2. 숲봇 전용 토큰을 24자 이상으로 만듭니다. 터미널을 쓸 수 있다면 `openssl rand -hex 24`처럼 예측하기 어려운 난수를 사용하세요.
3. 위 **Deploy with Vercel** 버튼을 누릅니다.
4. Vercel 입력란에 `OPENAI_API_KEY`와 `SOOPBOT_TOKEN`을 직접 입력해 배포합니다. 따옴표는 넣지 않습니다.
5. 배포가 끝나면 `https://<project>.vercel.app/api/reply`를 열어 `ok`가 보이는지 확인합니다.
6. [MacroDroid 설정 가이드](docs/macrodroid-setup.md)를 순서대로 따라 합니다.
7. 지정한 단톡방에서 `숲봇아 안녕`이라고 보내 답장이 한 번만 오는지 확인합니다.

배포 링크는 두 비밀값을 미리 채우지 않습니다. `SOOPBOT_TOKEN`은 OpenAI 키와 다른 임의 문자열이어야 하며, MacroDroid의 `X-Bot-Token` 헤더에도 같은 값을 사용합니다.

## 동작 구조

```text
카카오톡 알림 → 공폰 MacroDroid → 내 Vercel /api/reply
                                   → OpenAI Responses API
카카오톡 알림 답장 ← MacroDroid ← 일반 텍스트 답변
```

- 호출어 뒤의 질문과 같은 방의 최근 대화 몇 턴만 OpenAI에 전달합니다. 참고할 턴 수는 `SOOPBOT_MAX_HISTORY_TURNS`(기본 `4`)로 정하고, `0`으로 두면 예전처럼 한 질문씩 독립해서 답합니다.
- 도구 호출, 웹 검색, 데이터베이스, 공지·브리핑 기능은 포함하지 않습니다.
- 숲봇 애플리케이션과 Vercel 함수는 질문·답변을 데이터베이스나 애플리케이션 로그에 저장하지 않으며, OpenAI 요청에는 `store=False`를 사용합니다. 다만 최근 대화 몇 턴은 답변을 이어가기 위해 **warm Vercel 인스턴스의 메모리에만** 잠시 남습니다. 디스크에 쓰지 않고, 마지막 사용에서 **30분**이 지나거나 인스턴스가 종료되면 사라지며, 인스턴스끼리 공유되지 않습니다. 다만 [OpenAI 서비스의 데이터 처리 및 abuse monitoring 보존 정책](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint)은 별도로 적용될 수 있습니다. 개인정보나 비밀은 질문에 보내지 마세요.
- 최근 대화 기억, 같은 알림의 중복 억제, 분당 요청 제한은 모두 **warm Vercel 인스턴스별 best-effort 동작**입니다. 새 인스턴스가 시작되면 임시 상태가 초기화되고 인스턴스끼리 공유되지 않으므로, 이 설정은 내구성 있는 전역 rate limit이나 **전역 비용 상한이 아닙니다**. 실제 비용 관리는 위의 OpenAI 프로젝트 usage/spend limits와 알림을 사용하세요.
- 방 키 기본값은 `room1`입니다. 공개 URL을 알아도 전용 토큰이 없으면 답변을 요청할 수 없습니다.

## 원하는 이름과 말투로 바꾸기

호출어를 `숲봇아`에서 `나무야`로 바꾸려면 Vercel 환경변수와 MacroDroid 알림 조건을 **둘 다** 바꿔야 합니다. 말투, 모델, 방 키와 답변 길이를 포함한 전체 방법은 [맞춤 설정](docs/customize.md)을 참고하세요.

## 문제가 생겼다면

- 답이 없거나 `400`, `401`, `429`, `503`이 보일 때: [문제 해결](docs/troubleshooting.md)
- 키 노출 또는 보안 문제를 발견했을 때: [보안 정책](SECURITY.md)
- 로컬에서 검사할 때: Python 3.12와 [uv](https://docs.astral.sh/uv/getting-started/installation/)를 준비하고 `uv sync --locked --extra test` 후 `PYTHONPATH=src uv run --locked python -m unittest discover -s tests -v`

## 범위와 라이선스

숲봇은 한 방에서 안정적으로 질문에 답하는 최소 템플릿입니다. 브리핑, 웹사이트 아카이빙, 여러 방 관리 같은 기능은 이후 버전에서 검토합니다.

코드는 [MIT License](LICENSE)로 배포합니다.
