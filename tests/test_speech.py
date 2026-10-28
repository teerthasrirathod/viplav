from viplav.speech import SentenceChunker, SpeechCleaner


def stream(text, step=3):
    chunker = SentenceChunker()
    out = []
    for i in range(0, len(text), step):
        out += chunker.feed(text[i : i + step])
    if tail := chunker.flush():
        out.append(tail)
    return out


def test_splits_on_sentences_while_streaming():
    assert stream("Sure thing. The answer is 42! Want more?") == [
        "Sure thing.",
        "The answer is 42!",
        "Want more?",
    ]


def test_keeps_decimals_abbreviations_and_list_markers_together():
    text = "Dr. Smith measured 3.5 kg, e.g. a lot. Next: 1. first item here."
    assert stream(text) == ["Dr. Smith measured 3.5 kg, e.g. a lot.", "Next: 1. first item here."]


def test_waits_for_whitespace_before_cutting():
    chunker = SentenceChunker()
    assert chunker.feed("It costs $3.") == []  # could still become $3.50
    assert chunker.feed("50 today. ") == ["It costs $3.50 today."]


def test_breaks_very_long_run_ons_at_a_comma():
    text = ("word " * 30) + ", " + ("more " * 30)
    pieces = stream(text, step=50)
    assert len(pieces) >= 2
    assert all(len(p) <= 240 for p in pieces)


def test_cleaner_strips_markdown_and_skips_code_across_chunks():
    c = SpeechCleaner()
    assert c.clean("**Bold** and `x` with [docs](https://example.com).") == "Bold and x with docs."
    assert c.clean("Here it is: ```python\nprint(1)") == "Here it is: I've put the code on your screen."
    assert c.clean("still code") == ""
    assert c.clean("``` Done.") == "Done."


def test_cleaner_drops_bullets_and_urls():
    c = SpeechCleaner()
    assert c.clean("- first point") == "first point"
    assert c.clean("See https://x.y/z now") == "See the link on screen now"
    assert c.clean("---") == ""


def test_splits_on_devanagari_danda():
    assert stream("आज मौसम अच्छा है। चलो बाहर चलें।") == ["आज मौसम अच्छा है।", "चलो बाहर चलें।"]
