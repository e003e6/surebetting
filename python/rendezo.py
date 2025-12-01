from collections import defaultdict

from matek import calc_arb, van_arb



def get_parok(kulcsok):
    '''
    A lekérdzett kulcsokat r.keys() párokba rendezi ID alapján és szűri a lastupdate kulcsot
    Vissza adja a párokat egy listában [(id1, id2), (id3, id4) ... ]
    '''
    groups = defaultdict(list)
    
    for k in kulcsok:
        if k == "lastupdate":
            continue
    
        prefix = "-".join(k.split("-")[:4])
        groups[prefix].append(k)
    
    pairs = [tuple(v) for v in groups.values() if len(v) > 1]

    return pairs



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
    
    # d1 és d2 a két szótár
    for k in d1:
        pk = pair_key(k)
        if pk in d2:
            pairs.append((k, pk, d1[k], d2[pk]))
    
    for k in d2:
        pk = pair_key(k)
        if pk in d1:
            pairs.append((pk, k, d1[pk], d2[k]))
    
    return pairs


def cut_elotag(lista: list):
    return set([i.split('_', 1)[1] for i in lista])





# KIDOLGOZÁS ALATT...

def get_pos(iroda_1_data: dict, iroda_2_data: dict, toke=100_000, ksz=-2):
    kozoskulcsok = list(set(iroda_1_data.keys()) & set(iroda_2_data.keys()))

    for kulcs in kozoskulcsok:
        #print(kulcs)
        #print('\t', iroda_1_data[kulcs], iroda_2_data[kulcs], '\n')

        if kulcs == 'azsiai_hendikep':

            parok = parositas(iroda_1_data['azsiai_hendikep'], iroda_2_data['azsiai_hendikep'])
            #print(parok)
            for p in parok:
                if van_arb(p[2], p[3]):
                    print(kulcs)
                    print(p[0], p[1]) # cimek
                    print(p[2], p[3]) # oddsok
                    calc_arb(p[2], p[3], toke, ksz=ksz)

        # 3-as odds-ok
        elif kulcs in ['vegkimenetel']:
            pass

        # minden más
        else:
            a = iroda_1_data[kulcs]
            b = iroda_2_data[kulcs]

            keys = list(a.keys())          # ['igen', 'nem']
            k1, k2 = keys[0], keys[1]

            if van_arb(a[k1], b[k2]):
                print(kulcs)
                print(a[k1], b[k2])
                calc_arb(a[k1], b[k2], toke, ksz=ksz)
            
            if van_arb(a[k2], b[k1]):
                print(kulcs)
                print(a[k2], b[k1])
                calc_arb(a[k2], b[k1], toke, ksz=ksz)


