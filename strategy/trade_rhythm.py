"""TradeRhythmEngine & CostReducer placeholders."""


class TradeRhythmEngine:
    def __init__(self):
        self.stage = "INITIAL"

    def update(self, structure_state, position_state) -> str:
        return self.stage

    def next_action(self, structure_state, position_state) -> dict:
        return {"action": "hold", "quantity": 0, "reason": "placeholder"}
