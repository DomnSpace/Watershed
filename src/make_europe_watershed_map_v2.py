#!/usr/bin/env python3
"""V2 wrapper: refined outlet classifier for the Europe watershed map."""
import make_europe_watershed_map as base


def classify_terminal_v2(lon: float, lat: float, channel_as: str = "Atlantic Europe") -> str:
    # Caspian Europe is now a real class, not gray leftover.
    if 44.0 <= lon <= 70.5 and 38.0 <= lat < 62.5:
        return "Caspian Europe"

    # Polar / Arctic drainage.
    if lat >= 66.7:
        return "Polar Europe"
    if lat >= 63.0 and lon >= 20.0:
        return "Polar Europe"
    if lat >= 68.0 and lon >= 10.0:
        return "Polar Europe"

    # Black Sea, including Danube-class terminals that sit west/north of the literal coast.
    if 26.0 <= lon <= 43.8 and 40.0 <= lat <= 49.8:
        return "Black Sea Europe"
    if 20.0 <= lon < 26.0 and 43.0 <= lat <= 49.8:
        return "Black Sea Europe"

    # Baltic / East Sea widened southward for Poland, Oder, Vistula.
    if 9.0 <= lon <= 31.8 and 50.2 <= lat <= 66.7:
        return "Baltic / East Sea Europe"
    if 24.0 <= lon <= 32.8 and 58.0 <= lat <= 61.8:
        return "Baltic / East Sea Europe"

    # North Sea: Rhine, Maas/Meuse, Scheldt, Elbe/Weser, Jutland, eastern Britain.
    if -3.6 <= lon <= 11.8 and 50.0 <= lat <= 62.9:
        return "North Sea Europe"
    if 11.5 < lon <= 13.5 and 53.3 <= lat <= 57.2:
        return "North Sea Europe"
    if -4.2 <= lon <= 1.8 and 54.0 <= lat <= 60.9:
        return "North Sea Europe"

    # Channel policy, after Maas/Scheldt so they do not turn pink.
    if -6.5 <= lon <= 1.8 and 48.0 <= lat <= 50.9:
        return channel_as

    # Atlantic: north Spain, west France, Ireland, west Britain, Iceland.
    if -10.5 <= lon <= 1.8 and 41.2 <= lat <= 50.9:
        return "Atlantic Europe"
    if -12.0 <= lon <= -1.0 and 35.0 <= lat <= 43.8:
        return "Atlantic Europe"
    if lon <= -2.5 and 35.0 <= lat <= 66.8:
        return "Atlantic Europe"
    if -25.5 <= lon <= -10.0 and 63.0 <= lat <= 67.5:
        return "Atlantic Europe"

    # Mediterranean: deliberately evaluated after Atlantic to protect Biscay/Cantabrian basins.
    if -1.2 <= lon <= 37.5 and 34.0 <= lat <= 46.8:
        return "Mediterranean Europe"
    if -6.5 <= lon < -1.2 and 35.0 <= lat <= 41.2:
        return "Mediterranean Europe"
    if -3.5 <= lon <= 5.0 and 36.0 <= lat <= 43.5:
        return "Mediterranean Europe"

    # Norway Atlantic coast and islands not otherwise polar/north-sea.
    if 2.0 <= lon <= 20.0 and 58.0 <= lat < 66.7:
        return "Atlantic Europe"

    return "Unclassified / Other"


base.COLORS["Caspian Europe"] = "#c28b8b"
base.COLORS["Unclassified / Other"] = base.COLORS.pop("Caspian / Other", "#b7b7b7")
base.classify_terminal = classify_terminal_v2
base.main()
