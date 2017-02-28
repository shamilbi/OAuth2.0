from flask import (
    Flask, render_template, request, redirect, jsonify, url_for, flash,
    session as login_session, make_response)

from sqlalchemy import create_engine, asc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

import random
import string
import json
import requests
from oauth2client.client import flow_from_clientsecrets, FlowExchangeError

from database_setup import Base, Restaurant, MenuItem, User


def getUserId(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except SQLAlchemyError:
        return None


def createUser(d):
    'd = login_session'
    user = User(name=d['username'],
                email=d['email'],
                picture=d['picture'])
    session.add(user)
    session.commit()
    # user = session.query(User).filter_by(email=d['email']).one()
    # return user.id
    return getUserId(d['email'])

UNKNOWN_USER = User(name='unknown', email='', picture='')


def getUser(id_):
    if id_:
        return session.query(User).filter_by(id=id_).one()
    else:
        return UNKNOWN_USER

app = Flask(__name__)

# Google
G_CLIENT_SECRETS = 'g_client_secrets.json'

def _g_load_client_id():
    with open(G_CLIENT_SECRETS, 'r') as fp:
        return json.loads(fp.read())['web']['client_id']

G_CLIENT_ID = _g_load_client_id()
del _g_load_client_id

# Facebook
FB_CLIENT_SECRETS = 'fb_client_secrets.json'


def _fb_load_app_id():
    with open(FB_CLIENT_SECRETS, 'r') as fp:
        d = json.loads(fp.read())['web']
        return d['app_id'], d['app_secret'], d['app_version']

FB_APP_ID, FB_APP_SECRET, FB_APP_VERSION = _fb_load_app_id()
del _fb_load_app_id

#Connect to Database and create database session
engine = create_engine('sqlite:///restaurantmenu.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

@app.route('/login')
def showLogin():
    choices = string.ascii_uppercase + string.digits
    state = ''.join(random.choice(choices) for _ in range(32))
    login_session['state'] = state
    #return 'The current session state is %s' % state
    print('render login.html ...')
    return render_template('login.html', g_client_id=G_CLIENT_ID,
                           fb_app_id=FB_APP_ID, fb_app_version=FB_APP_VERSION)


def print2(s, *args):
    if not args:
        print(s)
    else:
        print(s % args)


def _mk_response(s, code):
    r = make_response(s, code)
    r.headers['Content-Type'] = 'text/html; charset=utf-8'
    return r


def _url_get0(url, **params):
    return requests.get(url, params=params)


def _url_get(url, **params):
    answer = requests.get(url, params=params)
    return json.loads(answer.text)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    print('gconnect ...')
    state1 = request.args.get('state')
    if state1 != login_session['state']:
        print2('bad state: %s ...', state1)
        return _mk_response('Invalid state parameter', 401)

    print('oauth flow ...')
    code = request.data
    try:
        oauth_flow = flow_from_clientsecrets(G_CLIENT_SECRETS, scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        return _mk_response('Failed to upgrade the authorization code', 401)

    print('tokeninfo ...')
    access_token = credentials.access_token
    result = _url_get('https://www.googleapis.com/oauth2/v1/tokeninfo',
                      access_token=access_token)

    error = result.get('error')
    print2('tokeninfo OK, error: %s', error)
    if error is not None:
        return _mk_response(error, 500)
    gplus_id = credentials.id_token['sub']
    print2('gplus_id: %s', gplus_id)
    if result['user_id'] != gplus_id:
        return _mk_response('Bad user_id', 401)
    if result['issued_to'] != G_CLIENT_ID:
        return _mk_response('Bad issued_to', 401)
    access_token2 = login_session.get('access_token')
    if access_token2 and access_token2 == access_token:
        return _mk_response('Current user is already connected', 200)

    print('userinfo ...')
    data = _url_get('https://www.googleapis.com/oauth2/v1/userinfo',
                    access_token=access_token)

    login_session['provider'] = 'google'
    login_session['access_token'] = access_token
    login_session['gplus_id'] = gplus_id
    login_session['username'] = data['name']
    login_session['email'] = data['email']
    login_session['picture'] = data['picture']

    print2('email: %s', data['email'])

    # check DB
    user_id = getUserId(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id
    print2('user created: %s', user_id)

    output = '''\
<h2>Welcome, %s!</h2>
<img src="%s" style="width: 300px; height: 300px; border-radius: 150px;"/>
''' % (login_session['username'], login_session['picture'])
    flash('you are now logged in as %s' % login_session['username'])
    print('gconnect: before return ...')
    return _mk_response(output, 200)


@app.route('/fbconnect', methods=['POST', ])
def fbconnect():
    state1 = request.args.get('state')
    if state1 != login_session['state']:
        print2('bad state: %s ...', state1)
        return _mk_response('Invalid state parameter', 401)
    access_token = request.data
    print('fb connect ...')
    result = _url_get0('https://graph.facebook.com/oauth/access_token',
                       grant_type='fb_exchange_token',
                       client_id=FB_APP_ID,
                       client_secret=FB_APP_SECRET,
                       fb_exchange_token=access_token)
    print2('fb result: %s', result.text)
    token = result.text.split('&')[0]

    print('fb connect 2 ...')
    data = _url_get('https://graph.facebook.com/v2.8/me?%s' % token)

    login_session['provider'] = 'facebook'
    login_session['facebook_id'] = data['id']
    login_session['access_token'] = access_token
    login_session['username'] = data['name']
    login_session['email'] = data['email']

LOGIN_KEYS = (
    'access_token', 'provider', 'gplus_id', 'facebook_id',
    'username', 'email', 'picture',
    'user_id')


def clear_session():
    for i in LOGIN_KEYS:
        if i in login_session:
            del login_session[i]


@app.route('/gdisconnect')
def gdisconnect():
    access_token = login_session.get('access_token')
    if access_token is None:
        return _mk_response('Current user not connected', 401)
    result = _url_get0('https://accounts.google.com/o/oauth2/revoke',
                       token=access_token)
    clear_session()
    if result.status_code == 200:
        return _mk_response('Successfully disconnected', 200)
    else:
        return _mk_response('Failed to revoke token for given user', 400)


def userLoggedIn():
    return 'access_token' in login_session


#JSON APIs to view Restaurant Information
@app.route('/restaurant/<int:restaurant_id>/menu/JSON')
def restaurantMenuJSON(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    items = session.query(MenuItem).filter_by(restaurant_id=restaurant_id).all()
    return jsonify(MenuItems=[i.serialize for i in items])


@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/JSON')
def menuItemJSON(restaurant_id, menu_id):
    Menu_Item = session.query(MenuItem).filter_by(id=menu_id).one()
    return jsonify(Menu_Item=Menu_Item.serialize)

@app.route('/restaurant/JSON')
def restaurantsJSON():
    restaurants = session.query(Restaurant).all()
    return jsonify(restaurants=[r.serialize for r in restaurants])


#Show all restaurants
@app.route('/')
@app.route('/restaurant/')
def showRestaurants():
    restaurants = session.query(Restaurant).order_by(asc(Restaurant.name))
    if userLoggedIn():
        html = 'restaurants.html'
    else:
        html = 'publicrestaurants.html'
    return render_template(html, restaurants=restaurants)

#Create a new restaurant
@app.route('/restaurant/new/', methods=['GET', 'POST'])
def newRestaurant():
  if not userLoggedIn():
      return redirect('/login')
  if request.method == 'POST':
      newR = Restaurant(name=request.form['name'],
                        user_id=login_session['user_id'])
      session.add(newR)
      flash('New Restaurant %s Successfully Created' % newR.name)
      session.commit()
      return redirect(url_for('showRestaurants'))
  else:
      return render_template('newRestaurant.html')

def validUser(restaurant):
    rUser = restaurant.user_id
    return rUser and rUser == login_session.get('user_id')


#Edit a restaurant
@app.route('/restaurant/<int:restaurant_id>/edit/', methods=['GET', 'POST'])
def editRestaurant(restaurant_id):
  if not userLoggedIn():
      return redirect('/login')
  editedRestaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
  if not validUser(editedRestaurant):
      return redirect(url_for('showRestaurants'))
  if request.method == 'POST':
      if request.form['name']:
          editedRestaurant.name = request.form['name']
          flash('Restaurant Successfully Edited %s' % editedRestaurant.name)
          return redirect(url_for('showRestaurants'))
  else:
      return render_template('editRestaurant.html', restaurant=editedRestaurant)


#Delete a restaurant
@app.route('/restaurant/<int:restaurant_id>/delete/', methods=['GET', 'POST'])
def deleteRestaurant(restaurant_id):
  if not userLoggedIn():
    return redirect('/login')
  restaurantToDelete = session.query(Restaurant).filter_by(id=restaurant_id).one()
  if not validUser(restaurantToDelete):
      return redirect(url_for('showRestaurants'))
  if request.method == 'POST':
    session.delete(restaurantToDelete)
    flash('%s Successfully Deleted' % restaurantToDelete.name)
    session.commit()
    return redirect(url_for('showRestaurants', restaurant_id=restaurant_id))
  else:
    return render_template('deleteRestaurant.html', restaurant=restaurantToDelete)

#Show a restaurant menu
@app.route('/restaurant/<int:restaurant_id>/')
@app.route('/restaurant/<int:restaurant_id>/menu/')
def showMenu(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    items = session.query(MenuItem).filter_by(restaurant_id=restaurant_id).all()
    creator = getUser(restaurant.user_id)
    if userLoggedIn():
        html = 'menu.html'
    else:
        html = 'publicmenu.html'
    return render_template(html, items=items, restaurant=restaurant,
                           creator=creator)



#Create a new menu item
@app.route('/restaurant/<int:restaurant_id>/menu/new/', methods=['GET', 'POST'])
def newMenuItem(restaurant_id):
    if not userLoggedIn():
        return redirect('/login')
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if not validUser(restaurant):
        return redirect(url_for('showMenu', restaurant_id=restaurant_id))
    if request.method == 'POST':
        newItem = MenuItem(name=request.form['name'],
                           description=request.form['description'],
                           price=request.form['price'],
                           course=request.form['course'],
                           restaurant_id=restaurant_id,
                           user_id=restaurant.user_id)
        session.add(newItem)
        session.commit()
        flash('New Menu %s Item Successfully Created' % (newItem.name))
        return redirect(url_for('showMenu', restaurant_id=restaurant_id))
    else:
        return render_template('newmenuitem.html', restaurant_id=restaurant_id)

#Edit a menu item
@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/edit', methods=['GET', 'POST'])
def editMenuItem(restaurant_id, menu_id):
    if not userLoggedIn():
        return redirect('/login')

    editedItem = session.query(MenuItem).filter_by(id=menu_id).one()
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if not validUser(restaurant):
        return redirect(url_for('showMenu', restaurant_id=restaurant_id))
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['price']:
            editedItem.price = request.form['price']
        if request.form['course']:
            editedItem.course = request.form['course']
        session.add(editedItem)
        session.commit()
        flash('Menu Item Successfully Edited')
        return redirect(url_for('showMenu', restaurant_id=restaurant_id))
    else:
        return render_template('editmenuitem.html',
                               restaurant_id=restaurant_id, menu_id=menu_id,
                               item=editedItem)


#Delete a menu item
@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/delete', methods=['GET', 'POST'])
def deleteMenuItem(restaurant_id, menu_id):
    if not userLoggedIn():
        return redirect('/login')
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if not validUser(restaurant):
        return redirect(url_for('showMenu', restaurant_id=restaurant_id))
    itemToDelete = session.query(MenuItem).filter_by(id=menu_id).one()
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('Menu Item Successfully Deleted')
        return redirect(url_for('showMenu', restaurant_id=restaurant_id))
    else:
        return render_template('deleteMenuItem.html', item=itemToDelete)


if __name__ == '__main__':
  app.secret_key = 'super_secret_key'
  app.debug = True
  app.run(host='0.0.0.0', port=5000)
