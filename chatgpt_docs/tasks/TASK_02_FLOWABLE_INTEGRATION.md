# TASK 02 — Flowable Integration

## Цель
Заменить placeholder workflow на BPMN/DMN.

## Реализовать
- BPMN и DMN v1;
- Process Adapter;
- start on ticket created;
- task list, claim, complete, reassign;
- WAITING 5 days;
- HOLD 15 days;
- approval branch;
- projection events;
- process audit;
- versioned deployment;
- UI tasks, queues, SLA, reassign, hold/resume.

## Acceptance
- один ticket → один process;
- DMN assignment;
- authorized completion;
- accelerated timer tests;
- no direct status edit;
- email response не закрывает;
- eventual projection;
- duplicate events safe.
