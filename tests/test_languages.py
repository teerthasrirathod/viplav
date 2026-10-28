import pytest

from viplav.languages import dominant_language, language_prompt, parse_languages, split_by_language


def test_single_language_stays_whole():
    assert split_by_language("नमस्ते, आप कैसे हैं?") == [("hi", "नमस्ते, आप कैसे हैं?")]
    assert split_by_language("All good, see you at 5.") == [("en", "All good, see you at 5.")]


def test_short_english_terms_stay_inside_hindi():
    assert split_by_language("मैं आज Python सीख रहा हूँ।") == [("hi", "मैं आज Python सीख रहा हूँ।")]


def test_long_runs_switch_voice():
    assert split_by_language("Let me explain this properly. ये बहुत ज़रूरी बात है।") == [
        ("en", "Let me explain this properly."),
        ("hi", "ये बहुत ज़रूरी बात है।"),
    ]


def test_three_languages_in_a_row():
    text = "Okay, here's the plan today. आज हम ये काम करेंगे. రేపు మనం మళ్ళీ కలుద్దాం."
    assert [lang for lang, _ in split_by_language(text)] == ["en", "hi", "te"]


def test_short_leading_word_joins_next_run():
    assert split_by_language("Yes, ये बिल्कुल सही है") == [("hi", "Yes, ये बिल्कुल सही है")]


def test_dominant_language():
    assert dominant_language("ok ठीक है भाई") == "hi"
    assert dominant_language("123") == "en"


def test_parse_languages_and_lambadi_script():
    langs = parse_languages("en,hi,te,lmn", "telugu")
    assert [l.code for l in langs] == ["en", "hi", "te", "lmn"]
    assert langs[-1].script == "Telugu" and langs[-1].voice_lang == "te"
    with pytest.raises(ValueError):
        parse_languages("en,xx")


def test_language_prompt_mentions_scripts_and_lambadi():
    prompt = language_prompt(parse_languages("en,hi,te,lmn"))
    assert "Hindi in Devanagari" in prompt and "Telugu in Telugu" in prompt
    assert "Lambadi (Gor Boli) has no standard script; write it in Devanagari" in prompt
    assert "Lambadi" not in language_prompt(parse_languages("en,hi"))
