"""Konstanter for KI Vann."""
from __future__ import annotations

DOMAIN = "ki_vann"
NAVN = "KI Vann"

# --- måler
CONF_MAALER = "maaler"                 # kumulativ vannmåler (m³ eller L)
CONF_ENHET = "enhet"                   # "m3" eller "L"
CONF_TIME_SENSOR = "time_sensor"       # valgfri: ferdig forbruk per time (L)

# --- soner med bevegelse
CONF_BAD = "bad"                       # bevegelse/nærvær på bad (dusj + håndvask)
CONF_DO = "do"                         # bevegelse/nærvær på do
CONF_KJOKKEN = "kjokken"               # bevegelse på kjøkken (oppvask for hånd)

# --- hvitevarer
CONF_VASKEMASKIN = "vaskemaskin"
CONF_OPPVASKMASKIN = "oppvaskmaskin"

# --- utendørs
CONF_HAGE = "hage"                     # bryter/ventil for vanning
CONF_HAGE_LITER = "hage_liter"         # valgfri: egen måler for vanning

# --- personer, brukes til å normalisere basisforbruket
CONF_PERSONER = "personer"             # liste med person/device_tracker/binary_sensor

# --- innstillinger
CONF_DUSJ_MIN = "dusj_min"             # minutter nærvær på bad før det regnes som dusj
CONF_OPPHOLD_GAP = "opphold_gap"       # minutter uten bevegelse som avslutter et opphold
CONF_PRIS = "pris"                     # kr per m³, vann og avløp samlet
CONF_LAERING = "laering"               # lær literprisene fra historikken?
CONF_VINDU_DAGER = "vindu_dager"       # hvor mange dager historikk læringen bruker

STD = {
    CONF_ENHET: "m3",
    CONF_DUSJ_MIN: 4.0,
    CONF_OPPHOLD_GAP: 3.0,
    CONF_PRIS: 45.0,
    CONF_LAERING: True,
    CONF_VINDU_DAGER: 60,
}

# Kategoriene vi fordeler på. Rekkefølgen er den de vises i.
KATEGORIER = ("dusj", "do", "handvask", "oppvask_hand", "vaskemaskin",
              "oppvaskmaskin", "hage", "basis")

KATEGORI_NAVN = {
    "dusj": "Dusj",
    "do": "Toalett",
    "handvask": "Håndvask",
    "oppvask_hand": "Oppvask og matlaging",
    "vaskemaskin": "Vaskemaskin",
    "oppvaskmaskin": "Oppvaskmaskin",
    "hage": "Utendørs",
    "basis": "Basis og udefinert",
}

KATEGORI_IKON = {
    "dusj": "mdi:shower-head",
    "do": "mdi:toilet",
    "handvask": "mdi:hand-wash-outline",
    "oppvask_hand": "mdi:silverware-clean",
    "vaskemaskin": "mdi:washing-machine",
    "oppvaskmaskin": "mdi:dishwasher",
    "hage": "mdi:sprinkler-variant",
    "basis": "mdi:water-outline",
}

# Startgjetning i liter per hendelse. Læringen flytter seg fra disse, men de holder
# modellen fornuftig de første dagene – og de fungerer som prior, så en kategori du
# nesten aldri bruker ikke havner på et vilt tall.
START_LITER = {
    "dusj": 60.0,            # 8 min à 7,5 L/min
    "do": 4.5,               # moderne dobbeltskyll
    "handvask": 2.0,
    "oppvask_hand": 12.0,
    "vaskemaskin": 48.0,     # per syklus
    "oppvaskmaskin": 11.0,   # per syklus
    "hage": 200.0,           # per vanningsøkt, overstyres av egen måler hvis du har
    "basis": 1.0,            # per time, uansett aktivitet (lekkasje, sisterne, is)
}

# Grenser læringen ikke går utenfor. Uten dem kan én rar time dra en kategori i grøfta.
GRENSER = {
    "dusj": (20.0, 150.0),
    "do": (2.0, 12.0),
    "handvask": (0.5, 8.0),
    "oppvask_hand": (2.0, 40.0),
    "vaskemaskin": (20.0, 90.0),
    "oppvaskmaskin": (5.0, 25.0),
    "hage": (20.0, 2000.0),
    "basis": (0.0, 30.0),
}

PRIOR_VEKT = 6.0        # hvor hardt startgjetningen holder igjen (i «antall timer»)

# Noen kategorier kan ikke skilles fra hverandre matematisk. Håndvask skjer nesten alltid
# sammen med en dusj eller en dotur, så de to er kollineære: modellen kan finne summen,
# men ikke fordelingen mellom dem. Da er det riktigere å holde håndvask nær
# startgjetningen og la dotur ta opp resten, enn å late som fordelingen er målt.
PRIOR_EKSTRA = {"handvask": 10.0}
LAER_HVER_MIN = 60      # hvor ofte modellen trenes på nytt
MAKS_RADER = 2400       # ca. 100 døgn med timer
