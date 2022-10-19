from sqlalchemy.testing.requirements import SuiteRequirements as SuiteRequirementsSQLA

class Requirements(SuiteRequirementsSQLA):
    def get_isolation_levels(self, config):
        return {"default": "SERIALIZABLE", "supported": ["SERIALIZABLE"]}
