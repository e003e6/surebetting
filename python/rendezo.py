from collections import defaultdict

from matek import calc_arb, van_arb



def get_parok(kulcsok):
    '''
    A lekérdezett kulcsokat meccs ID alapján csoportosítja és szűri a lastupdate kulcsot.
    Vissza adja azokat a csoportokat, amelyekben legalább 2 iroda kulcsa van.
    Egy csoport 2, 3 vagy több elemű is lehet (pl. mindhárom iroda írt ugyanarra a meccsre).
    Visszatérési érték: list[tuple[str, ...]]
    '''
    groups = defaultdict(list)

    for k in kulcsok:
        if k == "lastupdate":
            continue

        prefix = "-".join(k.split("-")[:4])
        groups[prefix].append(k)

    return [tuple(v) for v in groups.values() if len(v) > 1]



def parositas(d1, d2):
    '''
    A két iroda adatai közül a hendikep típusú elemeket párokba rendezi az állabi logika szerint:
    iroda1 csapat1 -0.25 - iroda 2 csapat 2 +0.25
    Vissza adja a párokat
    '''
    def pair_key(k: str) -> str:
        side, rest = k.split('_')      # pl. '1', '-0.25'
        sign = rest[0]                 # '-' vagy '+'
        num = rest[1:]                 # '0.25'
        other_side = '2' if side == '1' else '1'
        other_sign = '+' if sign == '-' else '-'
        return f"{other_side}_{other_sign}{num}"
    
    pairs = []

    # d1 és d2 a két szótár (csak d1-ből indulunk, így nem lesz dupla pár)
    for k in d1:
        pk = pair_key(k)
        if pk in d2:
            pairs.append((k, pk, d1[k], d2[pk]))

    return pairs


def cut_elotag(lista: list):
    return set([i.split('_', 1)[1] for i in lista])





# KIDOLGOZÁS ALATT...

def get_pos(iroda_1_data: dict, iroda_2_data: dict, toke=100_000, ksz=-2,
            iroda1_nev='Iroda 1', iroda2_nev='Iroda 2'):
    kozoskulcsok = list(set(iroda_1_data.keys()) & set(iroda_2_data.keys()))

    for kulcs in kozoskulcsok:

        # hendikep és ázsiai hendikep: ellentétes kimenetek párosítása (1_-X ↔ 2_+X)
        if kulcs in ('azsiai_hendikep', 'hendikep'):

            parok = parositas(iroda_1_data[kulcs], iroda_2_data[kulcs])
            for p in parok:
                if van_arb(p[2], p[3]):
                    print(kulcs)
                    print(f'{iroda1_nev}: {p[0]}   {iroda2_nev}: {p[1]}')
                    print(f'{iroda1_nev}: {p[2]}   {iroda2_nev}: {p[3]}')
                    calc_arb(p[2], p[3], toke, ksz=ksz,
                             iroda1_nev=iroda1_nev, iroda2_nev=iroda2_nev)

        # 3-as odds-ok
        elif kulcs in ['vegkimenetel']:
            pass

        # bináris piacok: igen/nem, alatt/felett, paros/paratlan, stb.
        else:
            a = iroda_1_data[kulcs]
            b = iroda_2_data[kulcs]

            if len(a) < 2 or len(b) < 2:
                continue

            # csak ELLENTÉTES kimeneteket nézünk: a-ból ka, b-ből a TÖBBI (≠ ka) kulcs
            for ka in a.keys():
                for kb in b.keys():
                    if ka == kb:
                        continue
                    if van_arb(a[ka], b[kb]):
                        print(kulcs)
                        print(f'{iroda1_nev}: {ka}   {iroda2_nev}: {kb}')
                        print(f'{iroda1_nev}: {a[ka]}   {iroda2_nev}: {b[kb]}')
                        calc_arb(a[ka], b[kb], toke, ksz=ksz,
                                 iroda1_nev=iroda1_nev, iroda2_nev=iroda2_nev)


