from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine

Base = declarative_base()


class User(Base):
    __tablename__ = 'user'

    id_ = Column('id', Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    email = Column(String(250), nullable=False)
    picture = Column(String(250))

    @property
    def serialize(self):
        return {'id': self.id_,
                'name': self.name,
                'email': self.email,
                'picture': self.picture}


class Restaurant(Base):
    __tablename__ = 'restaurant'

    id_ = Column('id', Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship(User)

    @property
    def serialize(self):
        return {'id': self.id_,
                'name': self.name,
                'user_id': self.user_id}


class MenuItem(Base):
    __tablename__ = 'menu_item'


    id_ = Column('id', Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    description = Column(String(250))
    price = Column(String(8))
    course = Column(String(250))
    restaurant_id = Column(Integer, ForeignKey('restaurant.id'))
    restaurant = relationship(Restaurant)
    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship(User)


    @property
    def serialize(self):
        return {'id': self.id_,
                'name': self.name,
                'description': self.description,
                'price': self.price,
                'course': self.course,
                'restaurant_id': self.restaurant_id,
                'user_id': self.user_id}



engine = create_engine('sqlite:///restaurantmenu.db')


Base.metadata.create_all(engine)
