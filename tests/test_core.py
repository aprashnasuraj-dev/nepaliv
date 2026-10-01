"""Run: pytest -q   (no TTS model or network needed)"""
from app.pipeline.composer import MelodyComposer
from app.pipeline.lyrics import _extract_json, template_lyrics, validate
from app.pipeline.nepali_text import count_syllables, rhymes, syllabify_word
from app.pipeline.styles import STYLES


def texts(word):
    return [s.text for s in syllabify_word(word)]


def test_schwa_deletion():
    assert texts("घर") == ["घर्"]                      # ghar
    assert texts("हिमालको") == ["हि", "माल्", "को"]     # hi-maal-ko
    assert texts("जन्मदिनको") == ["जन्", "म", "दिन्", "को"]
    assert texts("आउँछ") == ["आ", "उँ", "छ"]            # verb ending keeps schwa
    assert texts("धर्म") == ["धर्", "म"]
    assert texts("हिउँजस्तै") == ["हि", "उँ", "जस्", "तै"]


def test_counts_and_rhyme():
    assert count_syllables("माया लाग्छ तिमीलाई") == 8   # maa-yaa-laag-chha-ti-mi-laa-i
    assert rhymes("फूल फुल्यो बारीमा", "तिम्रै सम्झनामा")


def test_llm_json_validation():
    raw = '```json\n{"title":"माया","sections":[{"type":"verse","lines":["हिमालको हिउँजस्तै सेतो तिम्रो माया",' \
          '"खोलाको पानीझैँ बगिरहन्छ यो मन","चौतारीमा बसी सम्झन्छु तिमीलाई","बतासले ल्याउँछ तिम्रो मीठो बोली"]},' \
          '{"type":"chorus","lines":["माया लाग्छ तिमीलाई, साँचो माया लाग्छ","तिमीबिना अधुरो छ मेरो यो जीवन",' \
          '"माया लाग्छ तिमीलाई, साँचो माया लाग्छ","सधैँ सँगै हिँडौँ, यो जुनी र त्यो जुनी"]}]}\n```'
    lyrics, problems = validate(_extract_json(raw), "short")
    assert lyrics and len(lyrics["sections"]) == 2 and not problems
    bad, problems = validate({"sections": [{"type": "verse", "lines": ["I love you so much"]}]}, "short")
    assert bad is None and problems


def test_composer_deterministic_and_in_range():
    lyr = template_lyrics({"prompt": "birthday", "dedicate_to": "सीता"}, seed=1)
    order = [lyr["sections"][0], lyr["sections"][1]]
    for st in STYLES.values():
        a = MelodyComposer(st, 9, 60).compose(order)
        b = MelodyComposer(st, 9, 60).compose(order)
        assert [n.midi for n in a.vocal] == [n.midi for n in b.vocal]
        assert all(48 <= n.midi <= 76 for n in a.vocal)
        assert 20 < a.total_dur < 120
        assert all(x.start <= y.start for x, y in zip(a.vocal, a.vocal[1:]))


def test_line_segmentation_merges_glides():
    from app.pipeline.line_singer import segment
    # "डुल्नु" as espeak gives it: ɖ u l n u ʲ u  (extra glide vowel) -> must still be 2 syllables
    ph = ["ɖ", "ˈ", "u", "l", "n", "u", "ʲ", "u"]
    spans = [(p, i * 100, (i + 1) * 100) for i, p in enumerate(ph)]
    segs = segment(spans, [2])
    assert segs is not None and len(segs) == 2
    assert segs[1].start == 400                        # VC.CV split: "डुल् | नु"
