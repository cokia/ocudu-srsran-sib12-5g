class LabError(Exception):
    def __init__(self, code: str, detail: str, exit_code: int = 2):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.exit_code = exit_code
