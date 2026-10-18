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

### BAMF / Asylverfahren

Bei BAMF-Bescheiden, die mehrere Schutzformen nennen, gilt immer der
höchste zuerkannte Status: Asyl vor Flüchtlingseigenschaft vor
subsidiärem Schutz vor Abschiebungsverbot. Wird der Schutz aber von
einem Familienmitglied abgeleitet (Familienasyl oder internationaler
Familienschutz), gilt immer `familienasyl-familienschutz`.

Bei ablehnenden BAMF-Bescheiden gilt: Wird die Abschiebung in einen
anderen Dublin-Staat angeordnet, ist es immer
`dublin-ueberstellungsentscheidung`, auch wenn der Antrag als unzulässig
abgelehnt wird. Wird ein Antrag teils als offensichtlich unbegründet und
teils als einfach unbegründet abgelehnt, gilt `ablehnung-offensichtlich-unbegruendet`.

Schreiben, in denen das BAMF noch nichts entschieden hat (Einladungen,
Fragen, Aufforderungen, Protokolle), sind nie ein Bescheid mit
Entscheidung. Ordne sie dem passenden Schreiben-Typ zu, auch wenn darin
mögliche Folgen wie eine Ablehnung oder Einstellung erwähnt werden.

- `anhoerung-zulaessigkeit-termin`
  Das Schreiben ist eine Einladung des BAMF zu einem persönlichen
  Gespräch über die Zulässigkeit des Asylantrags. Es geht darum, ob ein
  anderer Staat zuständig ist, ob bereits in einem anderen Staat Schutz
  gewährt wurde oder ob ein anderer Staat als sicher gilt, nicht um die
  Fluchtgründe. Es nennt einen Termin mit Datum, Uhrzeit und Ort.

- `anhoerung-zulaessigkeit-schriftlich`
  Das Schreiben ist eine Aufforderung des BAMF, sich schriftlich zur
  Zulässigkeit des Asylantrags zu äußern. Es geht darum, ob ein anderer
  Staat zuständig ist, ob bereits in einem anderen Staat Schutz gewährt
  wurde oder ob ein anderer Staat als sicher gilt, nicht um die
  Fluchtgründe. Es nennt eine Frist für die Antwort, aber keinen Termin.

- `niederschrift-asylantragstellung`
  Das Schreiben ist die Niederschrift (das Protokoll) des BAMF über die
  förmliche Asylantragstellung. Es enthält die Personalien und erste
  Angaben der asylsuchenden Person, zum Beispiel zu Reiseweg, Familie
  und Dokumenten.

- `schriftliche-anhoerung`
  Das Schreiben ist eine Aufforderung des BAMF, sich schriftlich zu den
  Asylgründen oder zu bestimmten Fragen zu äußern, statt persönlich
  angehört zu werden. Es enthält meist Fragen oder einen Fragebogen und
  eine Frist für die Antwort.

- `aufforderung-betreiben-verfahren`
  Das Schreiben ist eine Aufforderung des BAMF, das Asylverfahren zu
  betreiben (Betreibensaufforderung), zum Beispiel Unterlagen zu schicken,
  sich zu äußern oder zu einem Termin zu kommen. Es warnt, dass der
  Asylantrag als zurückgenommen gilt und das Verfahren eingestellt wird,
  wenn die Person nicht innerhalb der Frist reagiert.

- `ladung-anhoerung`
  Das Schreiben ist eine Einladung des BAMF zur persönlichen Anhörung im
  Asylverfahren. Es nennt einen Termin, einen Ort und Hinweise zum Ablauf
  der Anhörung.

- `niederschrift-anhoerung`
  Das Schreiben ist die Niederschrift (das Protokoll) des BAMF über die
  persönliche Anhörung im Asylverfahren. Es gibt die Fragen des BAMF und
  die Antworten der asylsuchenden Person wieder.

- `anerkennung-asyl`
  Das Schreiben ist ein BAMF-Bescheid, nach dem die asylsuchende Person
  als Asylberechtigte anerkannt wird.

- `zuerkennung-fluechtlingseigenschaft`
  Das Schreiben ist ein BAMF-Bescheid, nach dem der asylsuchenden Person
  die Flüchtlingseigenschaft zuerkannt wird.

- `zuerkennung-subsidiaerer-schutzstatus`
  Das Schreiben ist ein BAMF-Bescheid, nach dem der asylsuchenden Person
  subsidiärer Schutz zuerkannt wird.

- `vorliegen-abschiebungsverbote`
  Das Schreiben ist ein BAMF-Bescheid, in dem festgestellt wird, dass ein
  Abschiebungsverbot vorliegt.

- `familienasyl-familienschutz`
  Das Schreiben ist ein BAMF-Bescheid, nach dem die Person Familienasyl
  oder internationalen Familienschutz bekommt. Der Schutz wird von einem
  Familienmitglied abgeleitet, das bereits Schutz bekommen hat, zum
  Beispiel Ehepartner, Eltern oder minderjährige Kinder.

- `ablehnung-einfach`
  Das Schreiben ist ein BAMF-Bescheid, nach dem der Asylantrag als
  (einfach) unbegründet abgelehnt wird. Es enthält eine Abschiebungs-
  androhung mit einer Ausreisefrist von in der Regel 30 Tagen.

- `ablehnung-offensichtlich-unbegruendet`
  Das Schreiben ist ein BAMF-Bescheid, nach dem der Asylantrag als
  offensichtlich unbegründet abgelehnt wird. Es enthält eine Abschiebungs-
  androhung mit einer verkürzten Ausreisefrist von in der Regel einer Woche.

- `ablehnung-unzulaessig`
  Das Schreiben ist ein BAMF-Bescheid, nach dem der Asylantrag als
  unzulässig abgelehnt wird, ohne dass die Asylgründe inhaltlich geprüft
  werden, zum Beispiel weil bereits in einem anderen Staat Schutz gewährt
  wurde oder ein Folgeantrag keine neuen Gründe enthält.

- `einstellungsbescheid`
  Das Schreiben ist ein BAMF-Bescheid, nach dem das Asylverfahren
  eingestellt wird, ohne über die Fluchtgründe zu entscheiden. Der
  Asylantrag gilt als zurückgenommen, zum Beispiel weil ein Termin
  verpasst oder eine Aufforderung nicht beantwortet wurde. Meist enthält
  er eine Abschiebungsandrohung.

- `entzug-widerruf-ruecknahme-ladung`
  Das Schreiben ist eine Einladung des BAMF zu einem persönlichen
  Gespräch, weil das BAMF prüft, ob es einen zuerkannten Schutz entzieht,
  widerruft oder zurücknimmt. Es nennt einen Termin mit Datum, Uhrzeit
  und Ort.

- `entzug-widerruf-ruecknahme-stellungnahme`
  Das Schreiben ist eine Aufforderung des BAMF, sich schriftlich zu
  äußern, weil das BAMF prüft, ob es einen zuerkannten Schutz entzieht,
  widerruft oder zurücknimmt. Es nennt eine Frist für die schriftliche
  Antwort, aber keinen Termin.

- `entzug-widerruf-ruecknahme-entscheidung`
  Das Schreiben ist ein BAMF-Bescheid, in dem ein zuerkannter Schutz
  entzogen, aberkannt, widerrufen oder zurückgenommen wird.

- `dublin-ueberstellungsentscheidung`
  Das Schreiben ist ein BAMF-Bescheid, nach dem ein anderer Dublin-Staat
  für das Asylverfahren zuständig ist. Es ordnet die Abschiebung
  (Überstellung) in diesen Staat an.

- `dublin-ueberstellungsfrist-verlaengert`
  Das Schreiben ist eine Mitteilung des BAMF im Dublin-Verfahren, dass
  die Frist für die Überstellung in den zuständigen Dublin-Staat
  verlängert wurde, zum Beispiel auf 18 Monate, weil die Person als
  flüchtig oder untergetaucht gilt.

- `dublin-ueberstellungsfrist-abgelaufen`
  Das Schreiben ist eine Mitteilung des BAMF im Dublin-Verfahren, dass
  die Überstellungsfrist abgelaufen ist. Deutschland ist jetzt für den
  Asylantrag zuständig, und das Asylverfahren wird in Deutschland
  weitergeführt. Oft wird dabei die frühere Dublin-Entscheidung
  aufgehoben.

- `abschlussmitteilung`
  Das Schreiben ist eine Mitteilung des BAMF, dass das Asylverfahren
  abgeschlossen ist und die Entscheidung unanfechtbar oder bestandskräftig
  geworden ist. Es enthält selbst keine neue Entscheidung über den
  Asylantrag.

### Andere Schreiben deutscher Behörden

- `sonstiges-schreiben`
  Das Schreiben ist ein lesbares, offizielles Schreiben einer deutschen
  Behörde, dessen Art du erkennst, das aber keinem der oben genannten
  Typen entspricht, zum Beispiel ein Schreiben der Ausländerbehörde, des
  Jobcenters, eines Gerichts oder ein anderes BAMF-Schreiben.

### Nicht erkannt

- `unsupported`
  Wähle diesen Typ nur, wenn der Bescheid nicht erkannt werden kann.
  Das gilt, wenn
  - der Text unvollständig, unleserlich oder durch ein schlechtes Foto
    stark verfälscht ist,
  - das Schreiben nicht von einer deutschen Behörde stammt,
  - du nicht erkennen kannst, was für ein Schreiben es ist.
  Rate nicht. Wenn du die Art des Schreibens nicht sicher erkennst, ist
  `unsupported` richtig.

## Response format

Return a JSON object with only these keys and no additional text:

{{
  "type": "<one of the slugs listed under Supported types>",
  "confidence": <float between 0.0 and 1.0>,
  "reason": "<one sentence, in the language of the document>"
}}

## Rules

1. `type` must be exactly one of the slugs listed under "Supported
   types", including `unsupported`.
2. `confidence` is your subjective probability that `type` is correct.
3. `reason` must be one sentence citing the single most decisive phrase
   from the document.

## Document text

---
{0}
---
"""

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
