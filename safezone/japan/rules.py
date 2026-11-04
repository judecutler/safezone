"""Official Japanese tsunami and shaking guidance, quoted verbatim, with a faithful English rendering and its source.

Only sentences an official source prints go in `Quote`. SafeZone's own wording (fallbacks, labels, disclaimers)
is English only, so no translation of official text is ever invented. Change a quote only against its source.
"""
from __future__ import annotations

from dataclasses import dataclass

SOURCES = {
    "cao_flyer": ("内閣府（防災担当）: 津波防災啓発チラシ (Cabinet Office, Disaster Management: tsunami flyer)",
                  "https://www.bousai.go.jp/kyoiku/poster/pdf/tsunami_flyer_nigetore.pdf"),
    "jma_tsunami": ("気象庁: 津波から身を守るために (JMA: Protecting yourself from tsunamis)",
                    "https://www.jma.go.jp/jma/kishou/know/jishin/tsunami_bosai/"),
    "jma_osaka_192": ("気象庁 大阪管区気象台: 地震一口メモ No.192 (JMA Osaka: earthquake memo 192)",
                      "https://www.data.jma.go.jp/osaka/jishinkazan/hitokuchi/192_tsunamihinan_202105.pdf"),
    "jma_eew": ("気象庁: 緊急地震速報の利用の心得 (JMA: How to act on an Earthquake Early Warning)",
                "https://www.data.jma.go.jp/svd/eew/data/nc/koudou/kokoroe.pdf"),
    "gsi_sites": ("国土地理院: 指定緊急避難場所・指定避難所データ (GSI: designated evacuation sites)",
                  "https://www.gsi.go.jp/bousaichiri/hinanbasho.html"),
    "portal_tiles": ("ハザードマップポータルサイト: オープンデータ (Hazard Map Portal: open data tiles)",
                     "https://disaportaldata.gsi.go.jp/hazardmap/copyright/opendata.html"),
    "mlit_legend": ("国土交通省: 水害ハザードマップ作成の手引き (MLIT: flood hazard map guide, depth colours p.37-38)",
                    "https://www.mlit.go.jp/river/basic_info/jigyo_keikaku/saigai/tisiki/hazardmap/suigai_hazardmap_tebiki_201604.pdf"),
}


@dataclass(frozen=True)
class Quote:
    ja: str
    """The official text, verbatim."""
    en: str
    """SafeZone's faithful English rendering of `ja`. Not an official translation."""
    source: str
    """Key into SOURCES."""

    def as_json(self) -> dict[str, str]:
        name, url = SOURCES[self.source]
        return {"ja": self.ja, "en": self.en, "source_name": name, "source_url": url}


# No line here asks anyone to move during shaking. JMA's household list also says to open a door to keep an
# exit and to deal with fire; both are actions during shaking, so SafeZone leaves them out.
DURING_SHAKING = [
    Quote("頭を保護し、大きな家具からは離れ、丈夫な机の下などに隠れる。",
          "Protect your head, keep away from large furniture, and take cover under something sturdy such as a desk.",
          "jma_eew"),
    Quote("あわてて外へ飛び出さない。", "Do not rush outside.", "jma_eew"),
]

GO_NOW = [
    Quote("強い揺れや弱くても長い揺れを感じたら、また地震を体で感じなくても、「津波警報」等を見聞きしたら、"
          "いち早く海岸から離れ、可能な限り高い場所へ避難",
          "If you feel strong shaking, or shaking that is weak but long, or if you see or hear a \"tsunami warning\" "
          "or similar even without feeling an earthquake, leave the coast as fast as you can and evacuate to the "
          "highest place you can reach.",
          "cao_flyer"),
    Quote("避難をする時は、近くの高台や津波避難タワー、津波避難ビルなどに避難",
          "When you evacuate, go to nearby high ground, a tsunami evacuation tower, a tsunami evacuation building "
          "or similar.",
          "cao_flyer"),
    Quote("原則として徒歩で避難して下さい。", "As a rule, evacuate on foot.", "jma_osaka_192"),
    Quote("見てから逃げるのでは間に合いません", "If you wait until you see it, you will not escape in time.",
          "jma_tsunami"),
]

STAY_AWAY = [
    Quote("津波は繰り返し襲ってきます。", "Tsunami waves strike again and again.", "jma_tsunami"),
    Quote("津波警報が出ている間は、絶対に戻ってはいけません。",
          "Never go back while a tsunami warning is in effect.", "jma_tsunami"),
    Quote("津波警報・注意報が解除され安全が確認されるまでは決して津波浸水の危険がある地域には立ち入らない",
          "Never enter areas at risk of tsunami flooding until the tsunami warning or advisory is lifted and "
          "safety is confirmed.",
          "cao_flyer"),
]

# SafeZone's own wording, English only.
NOT_IN_ZONE = (
    "This address is outside the tsunami inundation area mapped by the prefecture. If you are near the coast "
    "when strong or long shaking starts, still move to high ground."
)
NO_CHECKED_ROUTE = (
    "SafeZone could not check a route to a designated tsunami evacuation site from here. "
    "Move inland and to higher ground on foot, and follow local tsunami evacuation signs."
)
EVACUATION_BUILDING = "Evacuation building: go to the upper floors."
HIGH_GROUND = "Designated site outside the mapped inundation area."

DISCLAIMERS = [
    "SafeZone shows hazards it can see in your photos and flags from official public data. "
    "It is not a structural assessment and it does not have your building's plans.",
    "The inundation area and depth come from the prefecture's tsunami inundation assumption on Japan's Hazard Map "
    "Portal. Real tsunamis can go beyond it.",
    "Evacuation sites come from the municipality's designated emergency evacuation site list published by GSI. "
    "Routes are planning aids, not official evacuation routes.",
    "Official instructions, municipal hazard maps and local evacuation signs always override this app.",
]
