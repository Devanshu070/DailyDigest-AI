"""
Shared SQLAlchemy declarative Base.

Placed in its own module so all models and database-related code can
import the same Base without depending on models.__init__ or any
individual model module. This also avoids circular imports that would
occur if Base were defined in models.__init__.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
