class State:
    def __init__(self, name: str):
        self.name = name
        self.transitions: dict[str, str] = {}

    def add_transition(self, input_name: str, next_state: str):
        self.transitions[input_name] = next_state

    def __repr__(self) -> str:
        return str(self.__dict__)
