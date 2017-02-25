from flask import Flask, render_template, request, redirect, jsonify, url_for, flash

from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Restaurant, MenuItem

from flask import session as login_session
import random, string

from oauth2client.client import flow_from_clientsecrets, FlowExchangeError
import json
from flask import make_response
import requests

app = Flask(__name__)

CLIENT_SECRETS = 'client_secrets.json'

def _load_client_id():
    with open(CLIENT_SECRETS, 'r') as fp:
        return json.loads(fp.read())['web']['client_id']

CLIENT_ID = _load_client_id()
del _load_client_id

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
    return render_template('login.html')


def print2(s, *args):
    if not args:
        print(s)
    else:
        print(s % args)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    def _mk_response(s, code):
        r = make_response(s, code)
        r.headers['Content-Type'] = 'text/html; charset=utf-8'
        return r

    def _url_get(url, **params):
        answer = requests.get(url, params=params)
        return json.loads(answer.text)

    print('gconnect ...')
    state1 = request.args.get('state')
    if state1 != login_session['state']:
        print2('bad state: %s ...', state1)
        return _mk_response('Invalid state parameter', 401)

    print('oauth flow ...')
    code = request.data
    try:
        oauth_flow = flow_from_clientsecrets(CLIENT_SECRETS, scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        return _mk_response('Failed to upgrade the authorization code', 401)

    print('tokeninfo ...')
    result = _url_get('https://www.googleapis.com/oauth2/v1/tokeninfo',
                       access_token=credentials.access_token)

    error = result.get('error')
    print2('tokeninfo OK, error: %s', error)
    if error is not None:
        return _mk_response(error, 500)
    gplus_id = credentials.id_token['sub']
    print2('gplus_id: %s', gplus_id)
    if result['user_id'] != gplus_id:
        return _mk_response('Bad user_id', 401)
    if result['issued_to'] != CLIENT_ID:
        return _mk_response('Bad issued_to', 401)
    #stored_credentials = login_session.get('credentials')
    stored_gplus_id = login_session.get('gplus_id')
    #if stored_credentials is not None and gplus_id == stored_gplus_id:
    if stored_gplus_id and gplus_id == stored_gplus_id:
        return _mk_response('Current user is already connected', 200)
    #login_session['credentials'] = credentials
    login_session['gplus_id'] = gplus_id

    print('userinfo ...')
    data = _url_get('https://www.googleapis.com/oauth2/v1/userinfo',
                    access_token=credentials.access_token)

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']
    print2('email: %s', data['email'])

    output = '''\
<h2>Welcome, %s!</h2>
<img src="%s" style="width: 300px; height: 300px; border-radius: 150px;"/>
''' % (login_session['username'], login_session['picture'])
    print('gconnect: before return ...')
    return _mk_response(output, 200)



#JSON APIs to view Restaurant Information
@app.route('/restaurant/<int:restaurant_id>/menu/JSON')
def restaurantMenuJSON(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    items = session.query(MenuItem).filter_by(restaurant_id = restaurant_id).all()
    return jsonify(MenuItems=[i.serialize for i in items])


@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/JSON')
def menuItemJSON(restaurant_id, menu_id):
    Menu_Item = session.query(MenuItem).filter_by(id = menu_id).one()
    return jsonify(Menu_Item = Menu_Item.serialize)

@app.route('/restaurant/JSON')
def restaurantsJSON():
    restaurants = session.query(Restaurant).all()
    return jsonify(restaurants= [r.serialize for r in restaurants])


#Show all restaurants
@app.route('/')
@app.route('/restaurant/')
def showRestaurants():
  restaurants = session.query(Restaurant).order_by(asc(Restaurant.name))
  return render_template('restaurants.html', restaurants = restaurants)

#Create a new restaurant
@app.route('/restaurant/new/', methods=['GET','POST'])
def newRestaurant():
  if request.method == 'POST':
      newRestaurant = Restaurant(name = request.form['name'])
      session.add(newRestaurant)
      flash('New Restaurant %s Successfully Created' % newRestaurant.name)
      session.commit()
      return redirect(url_for('showRestaurants'))
  else:
      return render_template('newRestaurant.html')

#Edit a restaurant
@app.route('/restaurant/<int:restaurant_id>/edit/', methods = ['GET', 'POST'])
def editRestaurant(restaurant_id):
  editedRestaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
  if request.method == 'POST':
      if request.form['name']:
        editedRestaurant.name = request.form['name']
        flash('Restaurant Successfully Edited %s' % editedRestaurant.name)
        return redirect(url_for('showRestaurants'))
  else:
    return render_template('editRestaurant.html', restaurant = editedRestaurant)


#Delete a restaurant
@app.route('/restaurant/<int:restaurant_id>/delete/', methods = ['GET','POST'])
def deleteRestaurant(restaurant_id):
  restaurantToDelete = session.query(Restaurant).filter_by(id = restaurant_id).one()
  if request.method == 'POST':
    session.delete(restaurantToDelete)
    flash('%s Successfully Deleted' % restaurantToDelete.name)
    session.commit()
    return redirect(url_for('showRestaurants', restaurant_id = restaurant_id))
  else:
    return render_template('deleteRestaurant.html',restaurant = restaurantToDelete)

#Show a restaurant menu
@app.route('/restaurant/<int:restaurant_id>/')
@app.route('/restaurant/<int:restaurant_id>/menu/')
def showMenu(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    items = session.query(MenuItem).filter_by(restaurant_id = restaurant_id).all()
    return render_template('menu.html', items = items, restaurant = restaurant)
     


#Create a new menu item
@app.route('/restaurant/<int:restaurant_id>/menu/new/',methods=['GET','POST'])
def newMenuItem(restaurant_id):
  restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
  if request.method == 'POST':
      newItem = MenuItem(name = request.form['name'], description = request.form['description'], price = request.form['price'], course = request.form['course'], restaurant_id = restaurant_id)
      session.add(newItem)
      session.commit()
      flash('New Menu %s Item Successfully Created' % (newItem.name))
      return redirect(url_for('showMenu', restaurant_id = restaurant_id))
  else:
      return render_template('newmenuitem.html', restaurant_id = restaurant_id)

#Edit a menu item
@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/edit', methods=['GET','POST'])
def editMenuItem(restaurant_id, menu_id):

    editedItem = session.query(MenuItem).filter_by(id = menu_id).one()
    restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
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
        return redirect(url_for('showMenu', restaurant_id = restaurant_id))
    else:
        return render_template('editmenuitem.html', restaurant_id = restaurant_id, menu_id = menu_id, item = editedItem)


#Delete a menu item
@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/delete', methods = ['GET','POST'])
def deleteMenuItem(restaurant_id,menu_id):
    restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    itemToDelete = session.query(MenuItem).filter_by(id = menu_id).one() 
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('Menu Item Successfully Deleted')
        return redirect(url_for('showMenu', restaurant_id = restaurant_id))
    else:
        return render_template('deleteMenuItem.html', item = itemToDelete)




if __name__ == '__main__':
  app.secret_key = 'super_secret_key'
  app.debug = True
  app.run(host = '0.0.0.0', port = 5000)
