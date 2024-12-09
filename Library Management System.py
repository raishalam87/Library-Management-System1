from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import csv

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
auth = HTTPBasicAuth()

# Database Models

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(10), nullable=False)

    borrow_requests = db.relationship('BorrowRequest', backref='user', lazy=True)
    borrow_history = db.relationship('BorrowHistory', backref='user', lazy=True)


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    author = db.Column(db.String(120), nullable=False)
    isbn = db.Column(db.String(20), unique=True, nullable=False)

    borrow_requests = db.relationship('BorrowRequest', backref='book', lazy=True)
    borrow_history = db.relationship('BorrowHistory', backref='book', lazy=True)


class BorrowRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), default='pending')

    # Validate the date range when the request is created
    @staticmethod
    def validate_request(start_date, end_date, book_id):
        overlapping_request = BorrowRequest.query.filter(
            BorrowRequest.book_id == book_id,
            ((BorrowRequest.start_date <= end_date) & (BorrowRequest.end_date >= start_date))
        ).first()
        if overlapping_request:
            return False  # Book already borrowed in this period
        return True


class BorrowHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    borrowed_date = db.Column(db.Date, nullable=False, default=datetime.date.today)
    returned_date = db.Column(db.Date, nullable=True)

# Authentication function
@auth.verify_password
def verify_password(email, password):
    user = User.query.filter_by(email=email).first()
    if user and check_password_hash(user.password, password):
        return user

# API Endpoints

@app.route('/admin/users', methods=['POST'])
@auth.login_required
def create_user():
    if auth.current_user().role != 'admin':
        return jsonify({"message": "Forbidden"}), 403

    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')

    if not email or not password or not role:
        return jsonify({"message": "Missing fields"}), 400

    hashed_password = generate_password_hash(password)
    user = User(email=email, password=hashed_password, role=role)
    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "User created successfully"}), 201


@app.route('/admin/requests', methods=['GET'])
@auth.login_required
def view_requests():
    if auth.current_user().role != 'admin':
        return jsonify({"message": "Forbidden"}), 403

    requests = BorrowRequest.query.all()
    requests_data = [{"id": req.id, "user": req.user.email, "book": req.book.title, "start_date": req.start_date, "end_date": req.end_date, "status": req.status} for req in requests]
    return jsonify(requests_data), 200


@app.route('/admin/requests/<int:request_id>', methods=['PATCH'])
@auth.login_required
def approve_deny_request(request_id):
    if auth.current_user().role != 'admin':
        return jsonify({"message": "Forbidden"}), 403

    data = request.get_json()
    action = data.get('action')

    borrow_request = BorrowRequest.query.get(request_id)
    if not borrow_request:
        return jsonify({"message": "Request not found"}), 404

    if action not in ['approve', 'deny']:
        return jsonify({"message": "Invalid action"}), 400

    if action == 'approve':
        borrow_request.status = 'approved'
    else:
        borrow_request.status = 'denied'

    db.session.commit()

    return jsonify({"message": "Request updated successfully"}), 200


@app.route('/admin/history/<int:user_id>', methods=['GET'])
@auth.login_required
def view_user_history(user_id):
    if auth.current_user().role != 'admin':
        return jsonify({"message": "Forbidden"}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    history = BorrowHistory.query.filter_by(user_id=user_id).all()
    history_data = [{"book": hist.book.title, "borrowed_date": hist.borrowed_date, "returned_date": hist.returned_date} for hist in history]
    return jsonify(history_data), 200


@app.route('/books', methods=['GET'])
@auth.login_required
def get_books():
    books = Book.query.all()
    books_data = [{"id": book.id, "title": book.title, "author": book.author} for book in books]
    return jsonify(books_data), 200


@app.route('/requests', methods=['POST'])
@auth.login_required
def request_book():
    data = request.get_json()
    user_id = auth.current_user().id
    book_id = data.get('book_id')
    start_date = datetime.datetime.strptime(data.get('start_date'), "%Y-%m-%d").date()
    end_date = datetime.datetime.strptime(data.get('end_date'), "%Y-%m-%d").date()

    book = Book.query.get(book_id)
    if not book:
        return jsonify({"message": "Book not found"}), 404

    if not BorrowRequest.validate_request(start_date, end_date, book_id):
        return jsonify({"message": "Book already borrowed in this period"}), 400

    borrow_request = BorrowRequest(user_id=user_id, book_id=book_id, start_date=start_date, end_date=end_date)
    db.session.add(borrow_request)
    db.session.commit()

    return jsonify({"message": "Borrow request submitted successfully"}), 201


@app.route('/history', methods=['GET'])
@auth.login_required
def user_history():
    user_id = auth.current_user().id
    history = BorrowHistory.query.filter_by(user_id=user_id).all()
    history_data = [{"book": hist.book.title, "borrowed_date": hist.borrowed_date, "returned_date": hist.returned_date} for hist in history]
    return jsonify(history_data), 200

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)