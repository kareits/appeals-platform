# 07. AI-ready архитектура

## Будущие функции

- классификация документов;
- проверка недостающих документов;
- проект email-запроса;
- извлечение текста цифрового PDF;
- OCR печатного русского/казахского;
- экспериментальный рукописный OCR;
- извлечение полей;
- резюме;
- проект ответа;
- контролируемая auto-send для low-risk сценариев.

## Будущие сервисы

### Document Intelligence Service
PDF extraction, OCR, language/layout, classification, fields, confidence, review artifacts.

### AI Assistant Service
Summary, draft generation, template selection, rule compliance, source references, provider adapters.

## Human-in-the-loop

1. Recommendation only.
2. Send after employee approval.
3. Auto-send только allowlisted low-risk.

Без человека запрещены отказ, индивидуальное решение, изменение договора, закрытие и использование непроверенной рукописи.

## Комплектность

Требуемый комплект задается DMN/версионируемыми правилами. AI классифицирует полученные документы. `required - verified detected = missing`.

## AI audit

Capability, provider/model/version, prompt/template version, hashes, document IDs, structured result, confidence, warnings, corrections, approval, final text, latency, error.

## Security

AI не получает Exchange/DB credentials. Документы считаются недоверенными. Tool calls имеют узкие schemas. Recipient не формируется моделью. Отправка разрешается Flowable.

## Реализовать в MVP

Hashes, versions, document type, manual completeness, response draft history, feature flags, будущие schemas/events, отключенные AI service-task points.

Не реализовывать реальные LLM/OCR и autonomous send.
