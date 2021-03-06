import json

from sqlalchemy import Column, Float, ForeignKey, Integer, String, TypeDecorator, types
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

_Base = declarative_base()


class Json(TypeDecorator):
    @property
    def python_type(self):
        return object

    impl = types.String

    def process_bind_param(self, value, dialect):
        return json.dumps(value)

    def process_literal_param(self, value, dialect):
        return value

    def process_result_value(self, value, dialect):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None


class JobModel(_Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    name = Column(String)

    def __repr__(self):
        return f"Job<{self.id}, {self.name}"


class ExperimentModel(_Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True)
    job_id = Column(ForeignKey(JobModel.id), primary_key=True)
    job = relationship(JobModel, backref="models")
    state = Column(String)
    hash = Column(String)
    objective_result = Column(Float)
    requestor = Column(String)
    params = Column(Json)
    create_timestamp = Column(Float)
    finish_timestamp = Column(Float)
    metrics = Column(Json)
