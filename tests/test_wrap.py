import pytest

from builder.lib import calc, embed

PARTS = [{"when": [["bb_count__promise", "gte", 1]], "say": "A text message will confirm it."},
         {"when": [["bb_failed_out__promise", "present"]], "say": "I could not save one promise."},
         {"when": [["bb_transferred", "equals", "yes"]], "say": "A colleague takes over now."},
         {"say": "Thank you, goodbye."}]


@pytest.mark.parametrize("state,said", [
    ({"bb_count__promise": 2}, "A text message will confirm it. Thank you, goodbye."),
    ({"bb_count__promise": "1", "bb_failed_out__promise": "p2"},
     "A text message will confirm it. I could not save one promise. Thank you, goodbye."),
    ({"bb_count__promise": 0, "bb_transferred": "yes"}, "A colleague takes over now. Thank you, goodbye."),
    ({}, "Thank you, goodbye."),
])
def test_the_ending_words_follow_what_happened(state, said):
    assert embed.run(calc.wrap_code(parts=PARTS), state=state)["bb_wrap"] == said


@pytest.mark.parametrize("bad", [[], [{"say": ""}], [{"when": [["x", "true"]], "say": "a"}],
                                 [{"when": [["x", "nonsense"]], "say": "a"}, {"say": "b"}], [{"say": "{{x}}"}]])
def test_wrap_config_is_checked(bad):
    with pytest.raises(ValueError):
        calc.wrap_code(parts=bad)
