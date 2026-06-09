#!/usr/bin/env python3
"""V2 wrapper: refined outlet classifier for the Europe watershed map."""
import make_europe_watershed_map as base


def classify_terminal_v2(lon: float, lat: float, channel_as: str = "Atlantic Europe") -> str:
    # Caspian Europe is now a real class, not gray leftover. Extended southward
    # for Kura-Aras / south-Caspian edge cases visible on the Europe crop.
    if 44.0 <= lon <= 70.5 and 35.0 <= lat < 62.5:
        return "Caspian Europe"

    # Polar / Arctic drainage: Barents, White Sea, high Scandinavian and Russian north.
    if lat >= 66.7:
        return "Polar Europe"
    if lat >= 63.0 and lon >= 20.0:
        return "Polar Europe"
    if lat >= 68.0 and lon >= 10.0:
        return "Polar Europe"

    # Dardanelles / Marmara straits: a deliberately tiny separate outlet class.
    # This is not the Adriatic/Ionian Balkan coast; those remain Mediterranean.
    # It must run before the Black Sea window, otherwise the straits get swallowed.
    if 25.5 <= lon <= 30.4 and 39.4 <= lat <= 41.7:
        return "Dardanelles Europe"

    # Black Sea, including Danube-class terminals that sit west/north of the literal coast.
    if 26.0 <= lon <= 43.8 and 40.0 <= lat <= 49.8:
        return "Black Sea Europe"
    if 20.0 <= lon < 26.0 and 43.0 <= lat <= 49.8:
        return "Black Sea Europe"
    # Dardania / Morava-Serbia correction: most of this interior drains to the Danube.
    # Kept north of the Vardar/Aegean zone so Macedonia/Greek outlets stay Mediterranean.
    if 20.0 <= lon <= 22.9 and 42.0 <= lat <= 44.8:
        return "Black Sea Europe"

    # Guadalquivir / southwest Iberia must remain Atlantic, not Mediterranean.
    # This guard must run before the broad Spanish Mediterranean rule.
    if -8.5 <= lon <= -5.0 and 35.5 <= lat <= 39.4:
        return "Atlantic Europe"
    if -9.6 <= lon <= -6.5 and 36.0 <= lat <= 39.8:
        return "Atlantic Europe"

    # Iberian Mediterranean coast and Ebro/Catalonia protected from broad Atlantic rules.
    # Starts east of the Guadalquivir/Guadiana Atlantic window.
    if -5.0 < lon <= 3.7 and 35.0 <= lat <= 42.25:
        return "Mediterranean Europe"
    if -1.2 <= lon <= 37.5 and 34.0 <= lat <= 46.8:
        return "Mediterranean Europe"

    # North Sea must run before Baltic, otherwise Elbe/Hamburg/Jutland terminals get stolen.
    # Rhine, Maas/Meuse, Scheldt, Elbe, Weser, Ems, German Bight, west/south Denmark.
    if -3.6 <= lon <= 11.9 and 50.0 <= lat <= 63.0:
        return "North Sea Europe"
    if 11.5 < lon <= 13.5 and 53.3 <= lat <= 57.2:
        return "North Sea Europe"
    # Eastern Britain / east Scotland, with west Britain handled below as Atlantic.
    if -2.0 <= lon <= 2.0 and 52.0 <= lat <= 56.0:
        return "North Sea Europe"
    if -4.0 <= lon <= 2.0 and 56.0 <= lat <= 61.0:
        return "North Sea Europe"
    # SE Norway / Skagerrak-Oslofjord side.
    if 8.0 <= lon <= 12.8 and 57.5 <= lat <= 62.5:
        return "North Sea Europe"

    # Baltic / East Sea: Poland/Oder/Vistula, Baltic states, Gulf of Finland.
    # Starts east of the Elbe/Jutland danger zone for low latitudes.
    if 13.2 <= lon <= 31.8 and 50.2 <= lat <= 66.7:
        return "Baltic / East Sea Europe"
    if 9.0 <= lon < 13.2 and 56.8 <= lat <= 66.7:
        return "Baltic / East Sea Europe"
    if 24.0 <= lon <= 32.8 and 58.0 <= lat <= 61.8:
        return "Baltic / East Sea Europe"

    # Western Norway drains to Norwegian Sea / Atlantic margin, not the North Sea block.
    if 2.0 <= lon < 8.0 and 58.0 <= lat < 66.7:
        return "Atlantic Europe"

    # Atlantic Britain/Ireland: Liverpool-Manchester/Mersey, Irish Sea, west Scotland/Wales.
    if -8.8 <= lon < -2.0 and 50.0 <= lat <= 56.2:
        return "Atlantic Europe"
    if -8.8 <= lon < -4.0 and 56.0 <= lat <= 61.0:
        return "Atlantic Europe"

    # English Channel policy zone. This runs after Maas/Scheldt/Rhine and Britain rules.
    if -6.5 <= lon <= 1.8 and 48.0 <= lat <= 50.9:
        return channel_as

    # Atlantic: Cantabrian/Biscay north Spain and west France, but not Catalonia/Ebro.
    if -10.5 <= lon <= -1.2 and 42.25 <= lat <= 50.9:
        return "Atlantic Europe"
    if -12.0 <= lon <= -1.0 and 35.0 <= lat <= 43.8:
        return "Atlantic Europe"
    if lon <= -2.5 and 35.0 <= lat <= 66.8:
        return "Atlantic Europe"
    if -25.5 <= lon <= -10.0 and 63.0 <= lat <= 67.5:
        return "Atlantic Europe"

    return "Unclassified / Other"


def install_v2_classifier() -> None:
    base.COLORS["Caspian Europe"] = "#c28b8b"
    base.COLORS["Dardanelles Europe"] = "#e07a5f"
    base.COLORS["Unclassified / Other"] = base.COLORS.pop("Caspian / Other", "#b7b7b7")
    base.classify_terminal = classify_terminal_v2


if __name__ == "__main__":
    install_v2_classifier()
    base.main()
