# Bescheidcheck E2E test – Dublin decision

Model: `verdigado-think`  
Input: Dublin decision, 1 page  
HTTP result: 200

## Classification

`dublin_decision`

## Extraction

- authority: Bundesamt für Migration und Flüchtlinge
- document_type: dublin_decision
- required_action: null
- deadline_detected: false
- consequences:
  - Abschiebung nach Schweden
  - 3-month entry/residence ban from the date of deportation
- risk_level: high
- confidence: 1.0

## Timing

- OCR: 5.90 s
- classification: 27.73 s
- extraction: 45.95 s
- total: 79.63 s

## Result

PASS — real LLM end-to-end extraction works.

The 3-month entry/residence ban was correctly not interpreted as a deadline.