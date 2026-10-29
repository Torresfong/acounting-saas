"""In-memory fakes for the four ports. They record what callers send so tests can assert on it."""


class FakeGateway:
    def __init__(self):
        self.tins_validated = []

    def validate_tin(self, tin):
        self.tins_validated.append(tin)
        return True


class FakeAI:
    def __init__(self):
        self.extractions = []

    def extract(self, document, schema):
        self.extractions.append((document, schema))
        return {}


class FakeEmail:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject, "body": body})


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put(self, key, data):
        self.objects[key] = data

    def get(self, key):
        return self.objects[key]


class FakePorts:
    def __init__(self):
        self.gateway = FakeGateway()
        self.ai = FakeAI()
        self.email = FakeEmail()
        self.storage = FakeStorage()
