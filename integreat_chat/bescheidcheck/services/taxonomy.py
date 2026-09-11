"""Shared Bescheidcheck document taxonomy."""

import json
from typing import Final, Literal, Required, TypedDict

from django.conf import settings


class TaxonomyEntry(TypedDict, total=False):
    """Source taxonomy entry."""

    key: Required[str]
    kategorie: Required[Literal["BESCHEID", "NACHWEIS", "FORMULAR", "AKTION"]]
    aktion: Required[str]
    verwechslungsgefahr: Required[str]
    ebene: Required[Literal["E0", "E1", "E2", "E3", "E4", "E5"]]
    schweregrad: Required[Literal["KRITISCH", "HOCH", "MITTEL", "NIEDRIG"]]
    erkennungssignale: list[str]
    rechtsgrundlage: str


# Source: Klassifikations-Taxonomie_v3.html, version, August 2026.
# Whitespace is normalized; levels and severity come from headings and the legend.
BESCHEID_TAXONOMY: Final[dict[str, TaxonomyEntry]] = {
    "meldebescheinigung": {
        "key": "meldebescheinigung",
        "kategorie": "NACHWEIS",
        "aktion": "Aufbewahren; Basis für alles Weitere",
        "verwechslungsgefahr": (
            "„Brauche ich als EU-Bürger nicht\" — doch, Meldepflicht"
        ),
        "ebene": "E0",
        "schweregrad": "NIEDRIG",
    },
    "steuer_id": {
        "key": "steuer_id",
        "kategorie": "NACHWEIS",
        "aktion": "An Arbeitgeber/Familienkasse geben",
        "verwechslungsgefahr": "Mit Sozialversicherungsnr. verwechselt",
        "ebene": "E0",
        "schweregrad": "NIEDRIG",
    },
    "ankunftsnachweis": {
        "key": "ankunftsnachweis",
        "kategorie": "NACHWEIS",
        "aktion": "Mitführen",
        "verwechslungsgefahr": "Für Aufenthaltstitel/Entscheidung gehalten",
        "ebene": "E1",
        "schweregrad": "NIEDRIG",
    },
    "aufenthaltsgestattung": {
        "key": "aufenthaltsgestattung",
        "kategorie": "NACHWEIS",
        "aktion": "Vor Ablauf verlängern; Adressänderung melden",
        "verwechslungsgefahr": "Als dauerhafter Aufenthalt gedeutet",
        "ebene": "E1",
        "schweregrad": "MITTEL",
    },
    "zuweisungsbescheid": {
        "key": "zuweisungsbescheid",
        "kategorie": "BESCHEID",
        "aktion": "Zum Ort begeben; Umverteilung nur im Ausnahmefall",
        "verwechslungsgefahr": "Verbindlichkeit unterschätzt",
        "ebene": "E1",
        "schweregrad": "MITTEL",
    },
    "duldung": {
        "key": "duldung",
        "kategorie": "NACHWEIS",
        "aktion": (
            "Fristgerecht verlängern; Bleibewege prüfen; bei frischer Duldung nach "
            "Titelablauf: stiller Ablehnungsfall?"
        ),
        "verwechslungsgefahr": (
            "Für sicheren Status gehalten (bleibt ausreisepflichtig). Signal: eine "
            "neue Duldung direkt nach Ablauf eines § 104c-Titels (ohne Folgetitel § "
            "25a/25b) ist faktisch eine Ablehnung ohne Bescheid — der eigentliche "
            "Alarm, obwohl kein anfechtbares Dokument vorliegt."
        ),
        "ebene": "E1",
        "schweregrad": "HOCH",
    },
    "visum_national": {
        "key": "visum_national",
        "kategorie": "NACHWEIS",
        "aktion": "Vor Ablauf in eAT umwandeln; § im Visum = Zweck des späteren Titels",
        "verwechslungsgefahr": (
            "Für dauerhaften Status gehalten · Erteilungs-§ (z. B. 18a/18b/18g/20a) "
            "bestimmt Arbeitsumfang und eAT-Pfad"
        ),
        "ebene": "E1",
        "schweregrad": "MITTEL",
    },
    "chancenkarte": {
        "key": "chancenkarte",
        "kategorie": "NACHWEIS",
        "aktion": "Job suchen; Folge-Chancenkarte/Titel vor Ablauf beantragen",
        "verwechslungsgefahr": (
            "Such-Chancenkarte erlaubt nur Nebenbeschäftigung bis 20 Std./Woche + "
            "Probearbeit, keine Vollzeitstelle; Lebensunterhalt muss gesichert "
            "bleiben (§ 20a Abs. 4)"
        ),
        "ebene": "E1",
        "schweregrad": "MITTEL",
    },
    "visum_ablehnung": {
        "key": "visum_ablehnung",
        "kategorie": "BESCHEID",
        "aktion": "Klage VG Berlin oder neuer Antrag",
        "verwechslungsgefahr": (
            "Warten auf Remonstration (ab 07/2025 entfallen) · bei nationalem "
            "Fachkräftevisum ist „Zweifel an Rückkehrbereitschaft\" ein sachfremder "
            "Schengen-Maßstab — eigener Klageansatz"
        ),
        "ebene": "E1",
        "schweregrad": "HOCH",
    },
    "aufenthaltstitel_eat": {
        "key": "aufenthaltstitel_eat",
        "kategorie": "NACHWEIS",
        "aktion": "Befristung beachten; Zusatzblatt lesen; Jobverlust melden",
        "verwechslungsgefahr": (
            "Operative Bedingungen stehen auf dem Zusatzblatt (Beschäftigung "
            "gestattet?, Zweckbindung, Wohnsitzauflage); Nebenbestimmungen sind "
            "eigenständig anfechtbar (§ 12 AufenthG)"
        ),
        "ebene": "E1",
        "schweregrad": "HOCH",
    },
    "aufenthaltstitel_ablehnung": {
        "key": "aufenthaltstitel_ablehnung",
        "kategorie": "BESCHEID",
        "aktion": (
            "Sofort Beratung; Widerspruch/Klage binnen 1 Monat; Folgen-Antrag "
            "prüfen"
        ),
        "verwechslungsgefahr": (
            "Das negative Gegenstück zum eAT — wird ausreisepflichtig. Fehlte "
            "bisher im Modell. Bei Verlängerungs-Ablehnung Fiktionswirkung (§ 81) "
            "prüfen. A betrifft hier die ABH-Titelebene (anerkannte "
            "Schutzberechtigte § 25, Bleiberecht § 25a/25b/§ 23a/§ 104c), nicht die "
            "BAMF-Asylentscheidung. Achtung Mess-/Rechtsschutzlücke: Bei "
            "gescheitertem Übergang aus § 104c erscheint der negative Ausgang oft "
            "als stille Duldung statt als Bescheid — kein Dokument, keine Frist, "
            "kein Rechtsbehelf (s. duldung)."
        ),
        "ebene": "E1",
        "schweregrad": "KRITISCH",
    },
    "ausweisung": {
        "key": "ausweisung",
        "kategorie": "BESCHEID",
        "aktion": (
            "Sofort anwaltliche Beratung; Befristung des Einreiseverbots (§ 11) "
            "separat angreifen"
        ),
        "verwechslungsgefahr": (
            "Beendet auch einen bestehenden Titel und löst ein "
            "Einreise-/Aufenthaltsverbot aus; oft mit strafrechtlichem Hintergrund. "
            "Gilt nicht für freizügigkeitsberechtigte EU-Bürger — deren Pendant ist "
            "die Verlustfeststellung § 6 FreizügG/EU (s. verlustfeststellung)."
        ),
        "ebene": "E1",
        "schweregrad": "KRITISCH",
    },
    "titel_widerruf": {
        "key": "titel_widerruf",
        "kategorie": "BESCHEID",
        "aktion": "Widerspruch/Klage binnen 1 Monat; Vertrauensschutz vortragen",
        "verwechslungsgefahr": (
            "Widerruf (§ 52 AufenthG) bzw. Rücknahme (§ 48 VwVfG) eines erteilten "
            "Titels als bloße Mitteilung gelesen — ist anfechtbarer Bescheid"
        ),
        "ebene": "E1",
        "schweregrad": "HOCH",
    },
    "fiktionsbescheinigung": {
        "key": "fiktionsbescheinigung",
        "kategorie": "NACHWEIS",
        "aktion": "Antrag vor Titelablauf stellen; Reiserecht prüfen",
        "verwechslungsgefahr": "Erlaubt nicht immer Arbeit/Wiedereinreise (§-abhängig)",
        "ebene": "E1",
        "schweregrad": "HOCH",
    },
    "aufenthaltskarte": {
        "key": "aufenthaltskarte",
        "kategorie": "NACHWEIS",
        "aktion": "Beantragen; familiäre Bindung nachweisen",
        "verwechslungsgefahr": (
            "Nur deklaratorisch (§ 5 FreizügG/EU), kein Aufenthaltstitel — verleiht "
            "kein Recht, bescheinigt es nur. Verwechslung: Angehörige von "
            "EU-Bürgern (FreizügG/EU) vs. von Deutschen (AufenthG § 28). Eine "
            "Versagung ergeht als Verlustfeststellung/Nichtbestehens-Feststellung → "
            "s. verlustfeststellung."
        ),
        "ebene": "E1",
        "schweregrad": "MITTEL",
    },
    "daueraufenthaltskarte": {
        "key": "daueraufenthaltskarte",
        "kategorie": "NACHWEIS",
        "aktion": "Nach 5 Jahren beantragen",
        "verwechslungsgefahr": "Abgeleitetes Recht nicht weiter „vererbbar\"",
        "ebene": "E1",
        "schweregrad": "NIEDRIG",
    },
    "daueraufenthalt_bescheinigung": {
        "key": "daueraufenthalt_bescheinigung",
        "kategorie": "NACHWEIS",
        "aktion": "Optional als Nachweis anfordern",
        "verwechslungsgefahr": "Für zwingend nötig gehalten (ist freiwillig)",
        "ebene": "E1",
        "schweregrad": "NIEDRIG",
    },
    "niederlassungserlaubnis": {
        "key": "niederlassungserlaubnis",
        "kategorie": "NACHWEIS",
        "aktion": "Bei Erfüllung der Voraussetzungen beantragen",
        "verwechslungsgefahr": "Mit Einbürgerung verwechselt",
        "ebene": "E1",
        "schweregrad": "MITTEL",
    },
    "verlustfeststellung": {
        "key": "verlustfeststellung",
        "kategorie": "BESCHEID",
        "aktion": (
            "Sofort Beratung; je nach Grund Erwerbstätigkeit/Existenzmittel "
            "nachweisen → Aufhebung; § 7 Abs. 2-Befristung separat angreifen"
        ),
        "verwechslungsgefahr": (
            "„Als EU-Bürger kann mir nichts passieren\" — der einzige echte adverse "
            "Bescheid der E-Gruppe. Drei Grundlagen: § 5 Abs. 4 (Voraussetzungen "
            "entfallen), § 2 Abs. 7 (Scheinehe/gefälschte Dokumente), § 6 (öffentl. "
            "Ordnung/Sicherheit — sehr hoher Maßstab, Verurteilung allein genügt "
            "nicht)."
        ),
        "ebene": "E1",
        "schweregrad": "KRITISCH",
    },
    "aufenthalt_24_erteilung": {
        "key": "aufenthalt_24_erteilung",
        "kategorie": "NACHWEIS",
        "aktion": "Bei ABH abholen; Gültigkeitsdauer und Fortgeltungs-Stichtag prüfen",
        "verwechslungsgefahr": (
            "Als dauerhaft/unbefristet missverstanden — Geltung ist an "
            "EU-Ratsbeschlüsse gebunden (aktuell bis 4.3.2027, Verlängerung "
            "möglich)"
        ),
        "ebene": "E1",
        "schweregrad": "NIEDRIG",
    },
    "fortgeltung_24_mitteilung": {
        "key": "fortgeltung_24_mitteilung",
        "kategorie": "NACHWEIS",
        "aktion": "Kein Antrag nötig; bei Zweifel Termin bei ABH",
        "verwechslungsgefahr": (
            "Fehlende individuelle Bescheinigung wird als Statusverlust gedeutet — "
            "die Verlängerung gilt kollektiv per Rechtsverordnung, nicht per "
            "Einzelbescheid"
        ),
        "ebene": "E1",
        "schweregrad": "NIEDRIG",
    },
    "aufenthalt_24_ablehnung": {
        "key": "aufenthalt_24_ablehnung",
        "kategorie": "BESCHEID",
        "aktion": (
            "Sofort Beratung; Widerspruch oder Klage je nach Bundesland binnen 1 "
            "Monat"
        ),
        "verwechslungsgefahr": (
            "Betrifft nur Sonderfälle (Drittstaatsangehörige/Staatenlose ohne "
            "durchgängigen Aufenthalt in der Ukraine, CJEU-Urteil C-244/24 u.a. "
            "12/2024) — als Regelfall missverstanden, obwohl die große Mehrheit "
            "automatisch verlängert wird"
        ),
        "ebene": "E1",
        "schweregrad": "KRITISCH",
    },
    "anhoerung_ladung": {
        "key": "anhoerung_ladung",
        "kategorie": "NACHWEIS",
        "aktion": "Termin wahrnehmen; vorher Beratung",
        "verwechslungsgefahr": "Bedeutung des Termins unterschätzt",
        "ebene": "E2",
        "schweregrad": "HOCH",
    },
    "asyl_anerkennung": {
        "key": "asyl_anerkennung",
        "kategorie": "BESCHEID",
        "aktion": (
            "Titel bei ABH holen; *bei Teilversagung Klage auf höheren Schutz "
            "binnen 2 Wochen"
        ),
        "verwechslungsgefahr": (
            "Versteckte Teilablehnung (nur subsidiär statt Flüchtling) übersehen → "
            "2-Wochen-Frist verstreicht, schlechterer Status wird bestandskräftig. "
            "Severity hoch, sobald der Tenor mehr als eine Ziffer / eine Versagung "
            "trägt."
        ),
        "ebene": "E2",
        "schweregrad": "HOCH",
    },
    "asyl_ablehnung_einfach": {
        "key": "asyl_ablehnung_einfach",
        "kategorie": "BESCHEID",
        "aktion": "Klage erwägen; sofort Beratung",
        "verwechslungsgefahr": "Ablehnungsart in Tenor-Ziffer 1 nicht erkannt",
        "ebene": "E2",
        "schweregrad": "KRITISCH",
    },
    "asyl_ablehnung_ou": {
        "key": "asyl_ablehnung_ou",
        "kategorie": "BESCHEID",
        "aktion": "Klage und Eilantrag binnen 1 Woche",
        "verwechslungsgefahr": (
            "Eilantrag vergessen → Bescheid bleibt vollziehbar · „unzulässig\" ≠ nur "
            "Dublin: § 29 Abs. 1 Nr. 2 (Schutz in anderem EU-Staat) ergeht mit "
            "Abschiebungsandrohung + 1-Wochen-Frist — Unterfall asyl_unzulaessig "
            "getrennt führen"
        ),
        "ebene": "E2",
        "schweregrad": "KRITISCH",
    },
    "dublin_bescheid": {
        "key": "dublin_bescheid",
        "kategorie": "BESCHEID",
        "aktion": "Klage + Eilantrag binnen 1 Woche",
        "verwechslungsgefahr": (
            "Nicht als „echte\" Ablehnung erkannt · GEAS: heißt jetzt "
            "Zuständigkeitsbestimmungsverfahren — alter Treffer auf „Dublin\" reicht "
            "nicht mehr"
        ),
        "ebene": "E2",
        "schweregrad": "KRITISCH",
    },
    "asyl_widerruf": {
        "key": "asyl_widerruf",
        "kategorie": "BESCHEID",
        "aktion": "Sofort Beratung; Klage binnen 2 Wochen (§ 74 AsylG)",
        "verwechslungsgefahr": (
            "Statusüberprüfung/Widerruf (§ 73 AsylG) als bloße Information gelesen "
            "— es ist ein anfechtbarer Bescheid, der bereits zuerkannten Schutz "
            "beendet. Aktuell in großer Zahl (Länder-Reviews)."
        ),
        "ebene": "E2",
        "schweregrad": "KRITISCH",
    },
    "asyl_einstellung": {
        "key": "asyl_einstellung",
        "kategorie": "BESCHEID",
        "aktion": "Wiederaufnahmeantrag (§ 33 Abs. 5) oder Klage binnen 2 Wochen",
        "verwechslungsgefahr": (
            "Einstellung wegen Nichtbetreibens (§ 33 AsylG, z. B. verpasste "
            "Anhörung) als endgültiges Aus gelesen — Wiederaufnahme ist die "
            "eigentliche Handlung"
        ),
        "ebene": "E2",
        "schweregrad": "HOCH",
    },
    "dab": {
        "key": "dab",
        "kategorie": "NACHWEIS",
        "aktion": "Vor Einreise einholen",
        "verwechslungsgefahr": "Mit der Gleichwertigkeits-Anerkennung verwechselt",
        "ebene": "E3",
        "schweregrad": "MITTEL",
    },
    "zeugnisbewertung": {
        "key": "zeugnisbewertung",
        "kategorie": "NACHWEIS",
        "aktion": "Bei fehlendem anabin-Eintrag beantragen",
        "verwechslungsgefahr": "Ersetzt nicht die Anerkennung reglementierter Berufe",
        "ebene": "E3",
        "schweregrad": "NIEDRIG",
    },
    "anerkennungsbescheid": {
        "key": "anerkennungsbescheid",
        "kategorie": "BESCHEID",
        "aktion": "Für Beruf/Titel nutzen; ggf. Berufszulassung",
        "verwechslungsgefahr": "Gilt nur für den geprüften Referenzberuf",
        "ebene": "E3",
        "schweregrad": "MITTEL",
    },
    "defizitbescheid": {
        "key": "defizitbescheid",
        "kategorie": "BESCHEID",
        "aktion": "Benannte Lücken via Qualifizierung/Prüfung schließen",
        "verwechslungsgefahr": (
            "Als Ablehnung gelesen — ist Etappenziel zur Vollanerkennung"
        ),
        "ebene": "E3",
        "schweregrad": "HOCH",
    },
    "asylblg_bescheid": {
        "key": "asylblg_bescheid",
        "kategorie": "BESCHEID",
        "aktion": "Berechnung prüfen; bei Kürzung Widerspruch",
        "verwechslungsgefahr": (
            "Kürzungs-/Änderungsbescheid nicht als angreifbar erkannt Für U nur bei "
            "Einreise nach 1.4.2025 (Bürgergeld-Reform) — Regelfall bei U bleibt "
            "buergergeld_sgb2"
        ),
        "ebene": "E4",
        "schweregrad": "HOCH",
    },
    "bezahlkarte": {
        "key": "bezahlkarte",
        "kategorie": "NACHWEIS",
        "aktion": "Limits/Sperren lesen; bei Problemen Beratung",
        "verwechslungsgefahr": (
            "Leistungshöhe ändert sich nicht — nur Auszahlungsform Für U nur bei "
            "Einreise nach 1.4.2025, siehe asylblg_bescheid"
        ),
        "ebene": "E4",
        "schweregrad": "MITTEL",
    },
    "buergergeld_sgb2": {
        "key": "buergergeld_sgb2",
        "kategorie": "BESCHEID",
        "aktion": "Bei Ablehnung Rückausnahmen prüfen; Widerspruch",
        "verwechslungsgefahr": "EU: erhaltener Arbeitnehmerstatus übersehen",
        "ebene": "E4",
        "schweregrad": "HOCH",
    },
    "ueberbrueckung_sgb12": {
        "key": "ueberbrueckung_sgb12",
        "kategorie": "BESCHEID",
        "aktion": "Härtefallgründe vortragen; Widerspruch",
        "verwechslungsgefahr": (
            "Für reguläre Sozialhilfe gehalten (nur Notüberbrückung)"
        ),
        "ebene": "E4",
        "schweregrad": "HOCH",
    },
    "kindergeld_bescheid": {
        "key": "kindergeld_bescheid",
        "kategorie": "BESCHEID",
        "aktion": "Status nachweisen; Einspruch bei Aufhebung",
        "verwechslungsgefahr": (
            "Aufhebung als endgültig hingenommen; EU-Koordinierung unklar"
        ),
        "ebene": "E4",
        "schweregrad": "HOCH",
    },
    "kita_gebuehrenbescheid": {
        "key": "kita_gebuehrenbescheid",
        "kategorie": "BESCHEID",
        "aktion": (
            "Berechnung/Ermäßigungsstufe prüfen; Änderung der Verhältnisse melden"
        ),
        "verwechslungsgefahr": (
            "Als Rechnung ohne Widerspruchsmöglichkeit gelesen; Ermäßigungsanträge "
            "(Geschwister, Einkommen) übersehen. Format variiert je Kommune/Träger "
            "— keine bundeseinheitliche Rechtsgrundlage. Sprachbarriere ist "
            "zielgruppenunabhängig, nicht auf U beschränkt"
        ),
        "ebene": "E4",
        "schweregrad": "MITTEL",
    },
    "unterhaltsvorschuss_bescheid": {
        "key": "unterhaltsvorschuss_bescheid",
        "kategorie": "BESCHEID",
        "aktion": "Altersgrenze/Höchstbezugsdauer prüfen; bei Ablehnung Widerspruch",
        "verwechslungsgefahr": (
            "Rückgriffspflicht gegen den anderen Elternteil und Auskunftspflichten "
            "gegenüber dem Jugendamt unterschätzt"
        ),
        "ebene": "E4",
        "schweregrad": "HOCH",
    },
    "but_bescheid": {
        "key": "but_bescheid",
        "kategorie": "BESCHEID",
        "aktion": (
            "Einzelanträge je Leistungsart (Schulausflug, Mittagessen, Nachhilfe, "
            "Vereinsbeitrag) rechtzeitig stellen"
        ),
        "verwechslungsgefahr": (
            "Als einmaliger Pauschalbetrag missverstanden — tatsächlich mehrere "
            "getrennte Anträge (§28 SGB II bzw. §6b BKGG) mit eigenen "
            "Fristen/Nachweisen. Für F meist nur über Kinderzuschlag/Wohngeld (§6b "
            "BKGG) erreichbar, nicht über Jobcenter/Bürgergeld — Fachkräfte-Titel "
            "setzen i.d.R. Lebensunterhaltssicherung voraus"
        ),
        "ebene": "E4",
        "schweregrad": "MITTEL",
    },
    "schulanmeldung": {
        "key": "schulanmeldung",
        "kategorie": "FORMULAR",
        "aktion": (
            "Landesspezifische Fristen einhalten; Unterlagen (Impfnachweis, "
            "Voranmeldebescheinigung) vorbereiten"
        ),
        "verwechslungsgefahr": (
            "Meist kein anfechtbarer Bescheid, aber Fristversäumnis kann "
            "Schulplatzzuweisung verzögern — Kategorie (FORMULAR vs. BESCHEID) mit "
            "Lena vor Übernahme klären"
        ),
        "ebene": "E4",
        "schweregrad": "NIEDRIG",
    },
}


# Supported legacy types, separate from source catalog keys.
SUPPORTED_BESCHEID_TYPES: Final[frozenset[str]] = frozenset(
    settings.BESCHEID_SUPPORTED_TYPES
) - {"unsupported"}


class LegacyTaxonomyMapping(TypedDict):
    """Source entries and candidates for a legacy document type."""

    status: Literal["exact", "approximate", "unresolved"]
    source_keys: tuple[str, ...]
    candidate_source_keys: tuple[str, ...]
    note: str


LEGACY_TAXONOMY_MAPPINGS: Final[dict[str, LegacyTaxonomyMapping]] = {
    "anhörung-zur-zulässigkeit-persönlicher-termin": {
        "status": "approximate",
        "source_keys": ("anhoerung_ladung",),
        "candidate_source_keys": (),
        "note": (
            "Both describe a BAMF summons to a personal hearing. The source "
            "entry does not separate the Zulässigkeit hearing from the "
            "hearing on the grounds for asylum."
        ),
    },
    "anhörung-zur-zulässigkeit-schriftliche-antwort": {
        "status": "unresolved",
        "source_keys": (),
        "candidate_source_keys": ("anhoerung_ladung",),
        "note": (
            "The source catalog only records the summons to a personal "
            "hearing. A written request for a statement on Zulässigkeit has "
            "no catalog record; anhoerung_ladung is an overlap candidate "
            "because both belong to the same procedural step."
        ),
    },
    "niederschrift-zur-asylantragstellung": {
        "status": "unresolved",
        "source_keys": (),
        "candidate_source_keys": (),
        "note": (
            "The record of the formal asylum application has no catalog "
            "record; the source only covers decisions and summons."
        ),
    },
    "schriftliche-anhörung": {
        "status": "unresolved",
        "source_keys": (),
        "candidate_source_keys": ("anhoerung_ladung",),
        "note": (
            "A written hearing replaces the personal appointment recorded as "
            "anhoerung_ladung; the source does not record the written form "
            "as a separate entry."
        ),
    },
    "aufforderung-zum-betreiben-des-verfahrens": {
        "status": "unresolved",
        "source_keys": (),
        "candidate_source_keys": ("asyl_einstellung",),
        "note": (
            "The Betreibensaufforderung precedes the Einstellung recorded as "
            "asyl_einstellung but is not itself a decision. The source has "
            "no record for the request, so asyl_einstellung is an overlap "
            "candidate only."
        ),
    },
    "ladung-anhörung": {
        "status": "exact",
        "source_keys": ("anhoerung_ladung",),
        "candidate_source_keys": (),
        "note": (
            "Both identify the BAMF summons to the personal hearing. "
            "Exactness applies to document-type identity only."
        ),
    },
    "niederschrift-über-die-anhörung": {
        "status": "unresolved",
        "source_keys": (),
        "candidate_source_keys": ("anhoerung_ladung",),
        "note": (
            "The transcript of the hearing has no catalog record. "
            "anhoerung_ladung covers the summons to the same hearing and is "
            "an overlap candidate, not the same document."
        ),
    },
    "anerkennung-asyl": {
        "status": "approximate",
        "source_keys": ("asyl_anerkennung",),
        "candidate_source_keys": (),
        "note": (
            "asyl_anerkennung covers every grant of protection, including "
            "partial grants. It does not single out recognition as "
            "Asylberechtigte."
        ),
    },
    "zuerkennung-flüchtlingseigenschaft": {
        "status": "approximate",
        "source_keys": ("asyl_anerkennung",),
        "candidate_source_keys": (),
        "note": (
            "asyl_anerkennung covers every grant of protection and does not "
            "separate refugee status from the other forms."
        ),
    },
    "zuerkennung-subsidiärer-schutzstatus": {
        "status": "approximate",
        "source_keys": ("asyl_anerkennung",),
        "candidate_source_keys": (),
        "note": (
            "asyl_anerkennung records subsidiary protection as a possible "
            "partial grant rather than as its own document type."
        ),
    },
    "vorliegen-abschiebungsverbote": {
        "status": "approximate",
        "source_keys": ("asyl_anerkennung",),
        "candidate_source_keys": (),
        "note": (
            "A finding of an Abschiebungsverbot is the lowest form of the "
            "partial grant described by asyl_anerkennung; the source does "
            "not record it separately."
        ),
    },
    "familienasyl-familienschutz": {
        "status": "approximate",
        "source_keys": ("asyl_anerkennung",),
        "candidate_source_keys": (),
        "note": (
            "Derived family protection is a grant of protection covered by "
            "asyl_anerkennung; the source does not record the derivation "
            "from a family member."
        ),
    },
    "ablehnung-einfach": {
        "status": "exact",
        "source_keys": ("asyl_ablehnung_einfach",),
        "candidate_source_keys": (),
        "note": (
            "Both identify BAMF-Bescheid: einfache Ablehnung. "
            "Exactness applies to document-type identity only."
        ),
    },
    "ablehnung-offensichtlich-unbegründet-2": {
        "status": "exact",
        "source_keys": ("asyl_ablehnung_ou",),
        "candidate_source_keys": (),
        "note": (
            "Both identify the rejection as offensichtlich unbegründet with "
            "the shortened one-week deadline. Exactness applies to "
            "document-type identity only."
        ),
    },
    "ablehnung-unzulässig": {
        "status": "unresolved",
        "source_keys": (),
        "candidate_source_keys": ("asyl_ablehnung_ou", "dublin_bescheid"),
        "note": (
            "The source distinguishes non-Dublin inadmissibility from "
            "Dublin, and asyl_ablehnung_ou names that sub-case explicitly, "
            "but it records the offensichtlich unbegründet rejection. The "
            "source also mentions asyl_unzulaessig, but it has no catalog "
            "record, so no complete mapping can be selected. "
            "dublin_bescheid is an overlap candidate, not an asserted "
            "second target."
        ),
    },
    "einstellungsbescheid": {
        "status": "exact",
        "source_keys": ("asyl_einstellung",),
        "candidate_source_keys": (),
        "note": (
            "Both identify the decision discontinuing the asylum procedure. "
            "Exactness applies to document-type identity only."
        ),
    },
    "entzug-widerruf-rücknahme-ladung-zum-termin": {
        "status": "unresolved",
        "source_keys": (),
        "candidate_source_keys": ("asyl_widerruf", "anhoerung_ladung"),
        "note": (
            "The summons issued during a Widerrufsprüfung has no catalog "
            "record. asyl_widerruf covers the decision that may follow and "
            "anhoerung_ladung covers a summons in the main procedure; both "
            "are overlap candidates only."
        ),
    },
    "entzug-widerruf-rücknahme-aufforderung-zur-stellungnahme": {
        "status": "unresolved",
        "source_keys": (),
        "candidate_source_keys": ("asyl_widerruf",),
        "note": (
            "The written request for a statement during a Widerrufsprüfung "
            "has no catalog record; asyl_widerruf covers the decision that "
            "may follow and is an overlap candidate only."
        ),
    },
    "entzug-widerruf-rücknahme-entscheidung": {
        "status": "exact",
        "source_keys": ("asyl_widerruf",),
        "candidate_source_keys": (),
        "note": (
            "Both identify the decision withdrawing or revoking protection "
            "that was already granted. Exactness applies to document-type "
            "identity only."
        ),
    },
    "zuständigkeitsbestimmungsverfahren-dublin-überstellungsentscheidung": {
        "status": "exact",
        "source_keys": ("dublin_bescheid",),
        "candidate_source_keys": (),
        "note": (
            "Both identify the decision that another state is responsible "
            "and order the transfer. Exactness applies to document-type "
            "identity only."
        ),
    },
    "zuständigkeitsbestimmungsverfahren-dublin-überstellungsfrist-verlängert": {
        "status": "approximate",
        "source_keys": ("dublin_bescheid",),
        "candidate_source_keys": (),
        "note": (
            "The notice extending the transfer deadline belongs to the "
            "procedure recorded as dublin_bescheid, but it is a notice "
            "rather than the transfer decision itself."
        ),
    },
    "zuständigkeitsbestimmungsverfahren-dublin-überstellungsfrist-abgelaufen": {
        "status": "approximate",
        "source_keys": ("dublin_bescheid",),
        "candidate_source_keys": (),
        "note": (
            "The notice that the transfer deadline has expired belongs to "
            "the procedure recorded as dublin_bescheid, but it reverses the "
            "transfer decision instead of ordering it."
        ),
    },
    "bamf-abschlussmitteilung": {
        "status": "unresolved",
        "source_keys": (),
        "candidate_source_keys": (),
        "note": (
            "The notice that the procedure is final carries no decision of "
            "its own and has no catalog record."
        ),
    },
}


def render_taxonomy_context(document_type: str | None = None) -> str:
    """Return JSON context for one supported type, or all types if omitted."""
    context: list[dict[str, object]] = []
    if document_type is None:
        legacy_types = sorted(SUPPORTED_BESCHEID_TYPES)
    elif document_type in SUPPORTED_BESCHEID_TYPES:
        legacy_types = [document_type]
    else:
        legacy_types = []
    for legacy_type in legacy_types:
        mapping = LEGACY_TAXONOMY_MAPPINGS[legacy_type]
        record: dict[str, object] = {
            "legacy_type": legacy_type,
            "status": mapping["status"],
            "note": mapping["note"],
        }
        for field in ("source_keys", "candidate_source_keys"):
            sources = []
            for source_key in mapping[field]:
                entry = BESCHEID_TAXONOMY[source_key]
                sources.append(
                    {
                        name: entry[name]
                        for name in (
                            "key",
                            "kategorie",
                            "verwechslungsgefahr",
                            "erkennungssignale",
                            "rechtsgrundlage",
                        )
                        if name in entry
                    }
                )
            record[field] = sources
        context.append(record)
    return json.dumps(context, ensure_ascii=False, indent=2)


def render_classification_taxonomy_context() -> str:
    """Return taxonomy context for classification."""
    return render_taxonomy_context()


def is_supported_bescheid_type(document_type: str) -> bool:
    """Return whether a document type is supported by Bescheidcheck."""
    return document_type in SUPPORTED_BESCHEID_TYPES


def get_taxonomy_entry(document_type: str) -> TaxonomyEntry | None:
    """Look up a source taxonomy key."""
    return BESCHEID_TAXONOMY.get(document_type)
