

##  요구사항 

- 기술스택 
  - fastapi, python, asyncio.queue 
- 필수사항
  - fire_and_forget 형식의 함수를 처리하는 asyncio.event_queue를 구현해야함 
  - a2a protocol의 enqueue_event 처럼 queue 에넣고, 백그라운드로 처리하는 방식이여야함 
  - 예외처리는 필수로 들어가야하고 빈틈이 없어야함

- 불필요한 함수는 줄이고, 각 함수는 60자이내로 작성하세요.
- python 메모리누수같은 부분을 고려하여 작성하세요. 절대 메모리누수가 있어서는 안됩니다.
- 