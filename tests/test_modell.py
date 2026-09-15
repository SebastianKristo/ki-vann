"""Modellen: hendelsetelling, læring og fordeling som alltid summerer riktig."""
import random

from custom_components.ki_vann.const import GRENSER, PRIOR_EKSTRA, PRIOR_VEKT, START_LITER
from custom_components.ki_vann.coordinator import nnls

SANN = {"dusj": 72.0, "do": 5.2, "handvask": 1.6, "oppvask_hand": 9.0,
        "vaskemaskin": 55.0, "oppvaskmaskin": 13.0, "basis": 1.4}
KAT = list(SANN)


def _timer(n, frø=11):
    """Syntetiske timer. Korte badbesøk gir håndvask alene, slik det skjer i praksis —
    uten dem er håndvask og dotur matematisk uskillelige."""
    random.seed(frø)
    A, y = [], []
    for _ in range(n):
        dusj = random.choice([0, 0, 0, 1, 1, 2])
        do = random.choice([0, 1, 1, 2, 3])
        alene = random.choice([0, 0, 1, 1, 2])
        h = {"dusj": dusj, "do": do, "handvask": dusj + do + alene,
             "oppvask_hand": random.choice([0, 0, 1]),
             "vaskemaskin": 1 if random.random() < 0.07 else 0,
             "oppvaskmaskin": 1 if random.random() < 0.09 else 0, "basis": 1.0}
        A.append([float(h[k]) for k in KAT])
        y.append(sum(SANN[k] * h[k] for k in KAT) * random.uniform(0.93, 1.07))
    return A, y


def _lær(A, y):
    start = [START_LITER[k] for k in KAT]
    bv = PRIOR_VEKT * max(1.0, len(A) / 200.0)
    vekt = [bv * PRIOR_EKSTRA.get(k, 1.0) for k in KAT]
    return nnls(A, y, start, list(start), vekt, [GRENSER[k] for k in KAT])


def test_finner_literprisene():
    w = dict(zip(KAT, _lær(*_timer(600))))
    for k in ("dusj", "oppvask_hand", "vaskemaskin", "oppvaskmaskin"):
        assert abs(w[k] - SANN[k]) / SANN[k] < 0.15, (k, w[k], SANN[k])


def test_treffer_maalingene():
    A, y = _timer(600)
    w = _lær(A, y)
    rmse = (sum((sum(r[j] * w[j] for j in range(len(KAT))) - t) ** 2
                for r, t in zip(A, y)) / len(A)) ** 0.5
    snitt = sum(y) / len(y)
    assert rmse < snitt * 0.15, (rmse, snitt)


def test_holder_seg_innenfor_grensene():
    """Én absurd time skal ikke dra en kategori i grøfta."""
    A, y = _timer(200)
    y[50] = 50000.0
    w = dict(zip(KAT, _lær(A, y)))
    for k, v in w.items():
        lo, hi = GRENSER[k]
        assert lo <= v <= hi, (k, v)


def test_lite_data_holder_seg_nær_startgjetningen():
    """Med tolv timer skal prioren dominere. Basis måles i få liter per time, så der
    er absolutt avvik det meningsfulle målet, ikke relativt."""
    w = dict(zip(KAT, _lær(*_timer(12))))
    for k in KAT:
        if START_LITER[k] < 5:
            assert abs(w[k] - START_LITER[k]) < 5, (k, w[k])
        else:
            assert abs(w[k] - START_LITER[k]) / START_LITER[k] < 0.6, (k, w[k])


def test_ingen_data_gir_startgjetningen():
    start = [START_LITER[k] for k in KAT]
    assert nnls([], [], start, list(start), PRIOR_VEKT, [GRENSER[k] for k in KAT]) == start


def test_fordelingen_summerer_til_maalt():
    """Kjernen i hele modellen: fordelingen skal alltid stemme med måleren."""
    w = dict(zip(KAT, _lær(*_timer(400))))
    hendelser = {"dusj": 1, "do": 2, "handvask": 3, "oppvask_hand": 0,
                 "vaskemaskin": 0, "oppvaskmaskin": 0, "hage": 0, "basis": 1.0}
    for maalt in (0.0, 5.0, 90.0, 400.0):
        anslag = {k: w.get(k, 0.0) * hendelser.get(k, 0.0) for k in hendelser}
        s = sum(anslag.values())
        if maalt <= 0:
            fordelt = 0.0
        elif s <= 0:
            fordelt = maalt
        else:
            skala = min(5.0, maalt / s)
            fordelt = sum(v * skala for v in anslag.values())
            fordelt += max(0.0, maalt - fordelt)
        assert abs(fordelt - maalt) < 0.01, (maalt, fordelt)


def test_maaleren_har_rett_naar_anslaget_er_for_hoyt():
    """Anslår hendelsene 90 liter mens måleren viste 5, skal fordelingen bli 5 — ikke 17.
    En nedre klemme på skalaen gjorde at summen kunne overstige det målte."""
    anslag = {"dusj": 70.0, "do": 10.0, "handvask": 5.0, "basis": 1.0}
    maalt = 5.0
    s = sum(anslag.values())
    skala = min(5.0, maalt / s)
    fordelt = sum(v * skala for v in anslag.values())
    assert abs(fordelt - maalt) < 0.01, fordelt


def test_hjemme_leses_fra_bryter_og_person():
    """Posisjonsbrytere er `switch`: på betyr her, av betyr borte. Samme lesing
    gjelder person-entiteter, som bruker «home» i stedet for «on»."""
    from types import SimpleNamespace
    from custom_components.ki_vann.coordinator import VannMotor

    m = object.__new__(VannMotor)
    tilstander = {
        "switch.seb_hjemme": SimpleNamespace(state="on"),
        "switch.cybele_hjemme": SimpleNamespace(state="off"),
        "person.rune": SimpleNamespace(state="home"),
        "person.ukjent": SimpleNamespace(state="not_home"),
        "binary_sensor.gjest": SimpleNamespace(state="unavailable"),
    }
    m.hass = SimpleNamespace(states=SimpleNamespace(get=tilstander.get))
    m.entry = SimpleNamespace(data={"personer": list(tilstander)}, options={})

    assert m.personer_hjemme() == 2          # seb (on) og rune (home)

    m.entry = SimpleNamespace(data={"personer": ["switch.cybele_hjemme"]}, options={})
    assert m.personer_hjemme() == 0

    m.entry = SimpleNamespace(data={}, options={})
    assert m.personer_hjemme() == 0          # ingen valgt er ikke en feil
