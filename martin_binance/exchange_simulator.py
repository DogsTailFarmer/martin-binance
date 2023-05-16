from decimal import Decimal

class Funds:
    def __init__(self, base=dict, quote=dict):
        self.base = base
        self.quote = quote

    def get(self):
        return [self.base, self.quote]


class Account:
    def __init__(self, funds=Funds()):
        self.funds = funds
        self.fee_maker = Decimal('0')
        self.fee_taker = Decimal('0')


