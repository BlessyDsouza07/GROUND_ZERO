from abc import ABC, abstractmethod

class Adapter(ABC):
    @abstractmethod
    def collect(self):
        raise NotImplementedError
