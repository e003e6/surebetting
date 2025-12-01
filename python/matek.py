def van_arb(oddsA, oddsB):
    return (1/oddsA + 1/oddsB) < 1

def ep_tet_megoszlas(oddsA, oddsB):
    '''
    Kiszámolja, hogy egyenlő mértékű profit esetén mi a tét megoszlás
    Ha A nyer ugyan annyi nyereség mintha B nyerne
    És vissza adja a biztos nyereség arányát (min nyerség)
    '''
    ta = oddsB / (oddsA+oddsB)
    tb = 1-ta
    
    ny1, ny2 = (ta*oddsA)-1, (tb*oddsB)-1
    return ta, tb, min(ny1, ny2)


def calc_arb(oddsA, oddsB, toke, ksz=-3):

    # ellenőrizzük, hogy van-e arb opció
    if not van_arb(oddsA, oddsB):
        print('Nincsen arbitrázs opció!')
        return

    # kiszámoljuk a tiszta profitot
    ta, tb, profit = ep_tet_megoszlas(oddsA, oddsB)

    # mivel nem lehet nem kerek összeggel fogadni (vagy túl gyanús) kerekíteni kell kerek ezres vagy tízezres szintre
    # -3 = ezres szint, -4 tízezres szint
    fo_a = round(ta * toke, ksz)  # fogadás összege iroda A-nál
    fo_b = round(tb * toke, ksz)
    
    print('Iroda 1 tét:', '\t pontos:', int(ta * toke), '\t kerekített:', int(fo_a))
    print('Iroda 2 tét:', '\t pontos:', int(tb * toke), '\t kerekített:', int(fo_b))

    print()
    print('Matematikai biztos nyereség:', int(toke * profit))
    
    # nyereség kiszámítása kerekített öszegekkel
    t_v = fo_a + fo_b # a fogadásra költött összeg (a két fogadás árának összege)
    p_a, p_b = (fo_a*oddsA)-t_v, (fo_b*oddsB)-t_v
    b_ny = round(min(p_a, p_b))
    
    print('Biztos nyereség kerekített összeggel:', b_ny)
    print('Nereség A:', round(p_a), '\t nyereség B:', round(p_b))


