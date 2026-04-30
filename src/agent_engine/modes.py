from enum import Enum


class AgentMode(str, Enum):
    PERSONAL = "personal"
    COWORK = "cowork"
    TEAM = "team"
    MANAGEMENT = "management"
    KNOWLEDGE = "knowledge"
    EXECUTION = "execution"
    GOVERNANCE = "governance"

