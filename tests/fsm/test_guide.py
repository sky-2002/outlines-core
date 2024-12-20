import interegular
import pytest
from outlines_core.fsm.guide import Generate, RegexGuide, StopAtEOSGuide, Write


def assert_expected_tensor_ids(tensor, ids):
    assert len(tensor) == len(ids)
    norm_tensor = sorted(map(int, tensor))
    norm_ids = sorted(map(int, tensor))
    assert norm_tensor == norm_ids, (norm_tensor, norm_ids)


def test_stop_at_eos():
    class MockTokenizer:
        vocabulary = {"a": 1, "eos": 2}
        eos_token_id = 2

    fsm = StopAtEOSGuide(MockTokenizer())

    instruction = fsm.get_next_instruction(fsm.start_state)
    assert isinstance(instruction, Generate)
    assert instruction.tokens is None

    instruction = fsm.get_next_instruction(fsm.final_state)
    assert isinstance(instruction, Write)
    assert instruction.tokens == [2]

    assert fsm.get_next_state(fsm.start_state, 2) == fsm.final_state
    assert fsm.get_next_state(fsm.start_state, 1) == fsm.start_state
    assert fsm.is_final_state(fsm.start_state) is False
    assert fsm.is_final_state(fsm.final_state) is True


def test_regex_vocabulary_error():
    class MockTokenizer:
        vocabulary = {"a": 1}
        special_tokens = {"eos"}
        eos_token_id = 3

        def convert_token_to_string(self, token):
            return token

    regex_str = "[1-9]"

    with pytest.raises(ValueError, match="The vocabulary"):
        RegexGuide.from_regex(regex_str, MockTokenizer())


def test_from_regex():
    class MockTokenizer:
        vocabulary = {"1": 1, "a": 2, "eos": 3}
        special_tokens = {"eos"}
        eos_token_id = 3

        def convert_token_to_string(self, token):
            return token

    regex_str = "[1-9]"
    tokenizer = MockTokenizer()
    fsm = RegexGuide.from_regex(regex_str, tokenizer)

    assert fsm.get_index_dict() == {0: {1: 1}}

    instruction = fsm.get_next_instruction(-1)
    assert isinstance(instruction, Write)
    assert_expected_tensor_ids(instruction.tokens, [3])

    instruction = fsm.get_next_instruction(3)
    assert isinstance(instruction, Write)
    assert_expected_tensor_ids(instruction.tokens, [3])

    instruction = fsm.get_next_instruction(0)
    assert isinstance(instruction, Generate)
    assert_expected_tensor_ids(instruction.tokens, [1])

    assert fsm.get_next_state(state=0, token_id=1) == 1
    assert fsm.get_next_state(state=0, token_id=tokenizer.eos_token_id) == -1

    assert fsm.is_final_state(0) is False


def test_from_fsm():
    class MockTokenizer:
        vocabulary = {"1": 1, "a": 2, "eos": 3}
        special_tokens = {"eos"}
        eos_token_id = 3

        def convert_token_to_string(self, token):
            return token

    regex_str = "[1-9]"
    tokenizer = MockTokenizer()
    fsm = RegexGuide.from_interegular_fsm(
        interegular.parse_pattern(regex_str).to_fsm(), tokenizer
    )

    assert fsm.get_index_dict() == {0: {1: 1}}

    instruction = fsm.get_next_instruction(0)
    assert isinstance(instruction, Generate)
    assert_expected_tensor_ids(instruction.tokens, [1])

    assert fsm.get_next_state(state=0, token_id=1) == 1
    assert fsm.get_next_state(state=0, token_id=tokenizer.eos_token_id) == -1

    assert fsm.is_final_state(0) is False


def test_regex_multi_byte_llama_like():
    class MockTokenizer:
        vocabulary = {
            "1": 1,
            "a": 2,
            "eos": 3,
            "😍": 4,
            "<0xF0>": 5,
            "<0x9F>": 6,
            "<0x98>": 7,
            "<0x88>": 8,  # 😈
            "\ufffd": 9,
            "\ufffd\ufffd": 10,
        }
        special_tokens = {"eos"}
        eos_token_id = 3

        def convert_token_to_string(self, token):
            if token[0] == "<":
                return "\ufffd"
            return token

    regex_str = "[😁-😎]"
    tokenizer = MockTokenizer()
    fsm = RegexGuide.from_regex(regex_str, tokenizer)

    assert fsm.get_index_dict() == {
        0: {5: 1, 4: 2},
        1: {6: 3},
        3: {7: 4},
        4: {8: 2},
    }

    instruction = fsm.get_next_instruction(0)
    assert isinstance(instruction, Generate)
    assert_expected_tensor_ids(instruction.tokens, [5, 4])

    assert fsm.get_next_state(state=0, token_id=5) == 1
    assert fsm.get_next_state(state=0, token_id=tokenizer.eos_token_id) == -1

    assert fsm.is_final_state(0) is False


def test_regex_multi_byte_gpt2_like():
    class MockTokenizer:
        vocabulary = {
            "1": 1,
            "a": 2,
            "eos": 3,
            "😍": 4,
            " ": 5,
            "\ufffd": 6,
            "\ufffd\ufffd": 7,
            "ðŁĺ": 8,
            "Ī": 9,  # '😈'
            "Ġð": 10,
            "ŁĺĪ": 11,  # ' 😈'
        }
        special_tokens = {"eos"}
        eos_token_id = 3

        def convert_token_to_string(self, token):
            if self.vocabulary[token] >= 8:
                return "\ufffd"
            return token

    regex_str = " [😁-😎]"
    tokenizer = MockTokenizer()
    fsm = RegexGuide.from_regex(regex_str, tokenizer)

    assert fsm.get_index_dict() == {
        0: {5: 1, 10: 2},
        1: {8: 5, 4: 3},
        2: {11: 3},
        5: {9: 3},
    }

    instruction = fsm.get_next_instruction(0)
    assert isinstance(instruction, Generate)
    assert_expected_tensor_ids(instruction.tokens, [5, 10])

    assert fsm.get_next_state(state=0, token_id=5) == 1
    assert fsm.get_next_state(state=0, token_id=tokenizer.eos_token_id) == -1

    assert fsm.is_final_state(0) is False


def test_regex_final_state():
    """Make sure that the FSM stays in the final state as we keep generating"""

    class MockTokenizer:
        vocabulary = {"`": 101, ".": 102, "\n": 103, "eos": 104}
        special_tokens = {"eos"}
        eos_token_id = 104

        def convert_token_to_string(self, token):
            return token

    regex_str = r"`\n(\.\n)?`\n"
    tokenizer = MockTokenizer()
    fsm = RegexGuide.from_regex(regex_str, tokenizer)

    state = fsm.get_next_state(state=4, token_id=103)
    assert state == 5
    assert fsm.is_final_state(state)

    state = fsm.get_next_state(state=5, token_id=103)
    assert fsm.is_final_state(state)
