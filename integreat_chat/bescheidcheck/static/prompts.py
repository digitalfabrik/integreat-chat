"""
Static prompts for the bescheidcheck app.
"""

# pylint: disable=C0301,disable=R0903

from django.conf import settings

BACKGROUND = (
    f"You are a document classifier for the Integreat project "
    f"in {settings.INTEGREAT_COUNTRY}. "
    "You only ever see de-identified OCR'd text of German administrative "
    "letters (Bescheide). You do not have access to any personal data."
)

COUNSELING_SERVICE_BY_TYPE: dict[str, str] = {
    "bamf_simple_rejection": "Asylberatung",
    "obviously_unfounded_inadmissible": "Asylberatung",
    "dublin_decision": "Dublin Verfahren Beratung",
    "unsupported": "Allgemeine Migrationsberatung",
}


def counseling_question_for(
    question_language: str,
    bescheid_type: str,
    counseling_name: str | None = None,
) -> str:
    """
    Build a generic question asking where the user can find the
    counseling service relevant to the Bescheid type.

    ``counseling_name`` lets the caller pass in an already-localized
    service name so the final question is coherent in the chosen
    language.
    """
    name = counseling_name or COUNSELING_SERVICE_BY_TYPE.get(
        bescheid_type, "Flüchtlingsberatung / Asylberatung"
    )
    if question_language == "de":
        return f"Wo kann ich {name} finden?"
    return f"Where can I find {name}?"


class Prompts:
    """
    Collection of required prompts
    """

    BESCHEID_CLASSIFICATION = BACKGROUND + """
# Task

Classify the following German administrative letter (Bescheid) into exactly
one of the supported types. Do not try to guess beyond what the text says.

## Supported types

- `bamf_simple_rejection`
  A BAMF (Bundesamt für Migration und Flüchtlinge) "einfache Ablehnung"
  decision. Characteristic phrasing: "Ihr Asylantrag wird abgelehnt" with
  BAMF letterhead.

- `obviously_unfounded_inadmissible`
  A decision stating the application is "offensichtlich unbegründet" or
  "offensichtlich unzulässig", possibly by BAMF or another authority.

- `dublin_decision`
  A Dublin-III decision / Zuständigkeitsbestimmungsbescheid /
  Zuständigkeitsbestimmungsverfahren. The letter identifies another
  Schengen state as responsible for examining the asylum claim.

- `unsupported`
  Any other letter that does not match one of the three supported types.
  Examples: a positive acknowledgment (Anerkennung), a revocation
  (Widerruf / Rücknahme), an exclusion (Ausweisung), or a
  residence-permit refusal (Ablehnung Aufenthaltstitel).

## Supplemental taxonomy context

The following context describes relationships to the source catalog.
Source keys identify reference entries; they are never classification outputs.
Keep the supported legacy definitions above as the classification definitions.
For exact mappings, use the source context to help recognize the legacy type.
For approximate mappings, use it only as supplemental recognition context.
For unresolved mappings, candidate entries are disambiguation context only:
do not select a source mapping or treat candidates as equivalent legacy types.
Catalog warnings describe typical misunderstandings, not facts established
about this document. Use only evidence in the document for the classification.

{taxonomy_context}

## Response format

Return a JSON object with only these keys and no additional text:

{{
  "type": {allowed_types},
  "confidence": <float between 0.0 and 1.0>,
  "reason": "<one sentence, in the language of the document>"
}}

## Rules

1. `type` must be exactly one of the values listed above.
2. `confidence` is your subjective probability that `type` is correct.
3. `reason` must be one sentence citing the single most decisive phrase
   from the document.

## Document text

---
{0}
---
"""

    BESCHEID_EXTRACTION = (
        "You extract structured information from OCR'd German administrative "
        "documents (Bescheide).\n\n"
        "Rules:\n"
        "- Extract only information that is explicitly supported by the document.\n"
        "- Do not guess, invent, or complete missing facts.\n"
        "- Use null for missing scalar values.\n"
        "- Use [] for missing list values.\n"
        "- authority: the issuing authority, only if it can be identified from "
        "the document.\n"
        "- topic: a short description of the administrative topic supported by "
        "the document.\n"
        "- required_action: only an action explicitly required from the recipient; "
        "otherwise null.\n"
        "- requested_documents: include only documents explicitly requested from "
        "the recipient.\n"
        "- deadline_detected: true only if the document explicitly contains a "
        "deadline or time limit.\n"
        "- deadline_date: use YYYY-MM-DD only if a concrete calendar date is "
        "explicitly stated as the deadline. Do not calculate a date from relative "
        "phrases such as 'innerhalb einer Woche'.\n"
        "- deadline_text: preserve the original wording of the deadline or time "
        "limit from the document; otherwise null.\n"
        "- consequences: include only consequences explicitly stated in the "
        "document.\n"
        "- appointment: include appointment information only if explicitly stated; "
        "otherwise null.\n"
        "- legal_procedure: include only a legal remedy or procedure explicitly "
        "mentioned in the document; otherwise null.\n"
        "- risk_level: use only low, medium, or high based on information present "
        "in the document. If the level cannot be determined reliably, use null.\n"
        "- confidence: return a number from 0 to 1 representing confidence in the "
        "extracted information, not confidence in document classification.\n\n"
        "Classified document type: {bescheid_type}\n\n"
        "Supplemental taxonomy context:\n"
        "- The document text is authoritative for every extracted field.\n"
        "- Exact source mappings provide context only. Approximate mappings "
        "are supplemental context, not equivalent document definitions.\n"
        "- Unresolved candidate entries describe ambiguity only; do not "
        "select a candidate or resolve the mapping.\n"
        "- Do not copy or derive deadlines, actions, legal facts, consequences, "
        "or risk levels from taxonomy context. Extract them only when "
        "explicitly supported by the document text.\n"
        "- Keep the classified legacy document type; do not replace it "
        "with a source key or reclassify the document.\n\n"
        "{taxonomy_context}\n\n"
        "Document:\n{document_text}"
    )

    PAGE_ORDERING = BACKGROUND + """
# Task

You will receive short summaries of several pages of a German
administrative letter (Bescheid). The pages may not be in reading order.
Identify the correct reading order by reasoning about the letter
structure (e.g. header/notice first, main decision in the middle,
legal remedies / signature page last).

Strict response rules (the parser is unforgiving):
1. Your final answer must be a single line of comma-separated 1-based
   page indices, e.g. `2,1,3`. No other text, labels, or punctuation.
2. Every page index from 1 to the total number of pages must appear
   exactly once. Do not repeat an index, do not skip one, and do not
   invent one.
3. Use 1-based numbering, matching the `[page N]` labels in the input.
4. Any explanatory reasoning must come *before* the single answer line;
   only that line will be parsed.

Summaries of all {1} pages are provided below.

---
{0}
---

Answer (final line only, e.g. `2,1,3`):
"""
