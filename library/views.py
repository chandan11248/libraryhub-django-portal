from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count

from .models import Book, Category, BorrowRecord, ActivityLog
from .forms import BookForm, CategoryForm, UserRegistrationForm, SearchForm


# ============================================================
# REQUEST & RESPONSE HANDLING
# ============================================================

def home(request):
    """
    Home page - demonstrates handling GET requests, template rendering,
    and session data (visit counter from middleware).
    """
    books = Book.objects.select_related('category').all()[:6]
    categories = Category.objects.annotate(book_count=Count('books'))
    total_books = Book.objects.count()
    total_categories = Category.objects.count()

    context = {
        'books': books,
        'categories': categories,
        'total_books': total_books,
        'total_categories': total_categories,
        'visit_count': request.session.get('visit_count', 0),
        'last_visit': request.session.get('last_visit', 'First visit'),
    }
    return render(request, 'library/home.html', context)


def book_list(request):
    """
    Book listing with search - demonstrates GET request handling,
    query parameters, and form processing.
    """
    form = SearchForm(request.GET)
    books = Book.objects.select_related('category').all()

    if form.is_valid():
        query = form.cleaned_data.get('query')
        category = form.cleaned_data.get('category')

        if query:
            books = books.filter(
                Q(title__icontains=query) | Q(author__icontains=query)
            )
        if category:
            books = books.filter(category=category)

    context = {
        'books': books,
        'form': form,
        'result_count': books.count(),
    }
    return render(request, 'library/book_list.html', context)


def book_detail(request, pk):
    """
    Book detail - demonstrates URL parameter handling and dynamic routing.
    """
    book = get_object_or_404(Book, pk=pk)
    related_books = Book.objects.filter(category=book.category).exclude(pk=pk)[:4]

    context = {
        'book': book,
        'related_books': related_books,
    }
    return render(request, 'library/book_detail.html', context)


# ============================================================
# CRUD OPERATIONS (Create, Read, Update, Delete)
# ============================================================

@login_required
def book_create(request):
    """
    Create a new book - demonstrates POST request handling,
    form validation, and CSRF protection.
    """
    if request.method == 'POST':
        form = BookForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Book added successfully!')
            return redirect('book_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BookForm()

    return render(request, 'library/book_form.html', {'form': form, 'action': 'Add'})


@login_required
def book_update(request, pk):
    """
    Update existing book - demonstrates PUT-like request handling with forms.
    """
    book = get_object_or_404(Book, pk=pk)

    if request.method == 'POST':
        form = BookForm(request.POST, instance=book)
        if form.is_valid():
            form.save()
            messages.success(request, f'"{book.title}" updated successfully!')
            return redirect('book_detail', pk=pk)
    else:
        form = BookForm(instance=book)

    return render(request, 'library/book_form.html', {'form': form, 'action': 'Update', 'book': book})


@login_required
def book_delete(request, pk):
    """
    Delete a book - demonstrates DELETE operation with confirmation.
    """
    book = get_object_or_404(Book, pk=pk)

    if request.method == 'POST':
        title = book.title
        book.delete()
        messages.success(request, f'"{title}" deleted successfully!')
        return redirect('book_list')

    return render(request, 'library/book_confirm_delete.html', {'book': book})


# ============================================================
# CATEGORY MANAGEMENT
# ============================================================

@login_required
def category_create(request):
    """Create a new category."""
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category created successfully!')
            return redirect('home')
    else:
        form = CategoryForm()

    return render(request, 'library/category_form.html', {'form': form})


# ============================================================
# BORROW / RETURN (Session-based & Auth-required)
# ============================================================

@login_required
def borrow_book(request, pk):
    """
    Borrow a book - demonstrates session tracking and authenticated operations.
    """
    book = get_object_or_404(Book, pk=pk)

    if book.copies_available <= 0:
        messages.warning(request, f'"{book.title}" is not available for borrowing.')
        return redirect('book_detail', pk=pk)

    # Check if already borrowed
    existing = BorrowRecord.objects.filter(user=request.user, book=book, status='borrowed').first()
    if existing:
        messages.info(request, f'You have already borrowed "{book.title}".')
        return redirect('book_detail', pk=pk)

    # Create borrow record and update availability
    BorrowRecord.objects.create(user=request.user, book=book)
    book.copies_available -= 1
    book.save()

    # Track in session
    borrowed_books = request.session.get('borrowed_books', [])
    borrowed_books.append(book.title)
    request.session['borrowed_books'] = borrowed_books

    messages.success(request, f'You have borrowed "{book.title}".')
    return redirect('my_books')


@login_required
def return_book(request, pk):
    """
    Return a borrowed book - demonstrates session and DB update.
    """
    record = get_object_or_404(BorrowRecord, pk=pk, user=request.user, status='borrowed')

    record.status = 'returned'
    record.return_date = timezone.now()
    record.save()

    record.book.copies_available += 1
    record.book.save()

    messages.success(request, f'"{record.book.title}" returned successfully!')
    return redirect('my_books')


@login_required
def my_books(request):
    """
    User's borrowed books - demonstrates authenticated user-specific queries.
    """
    records = BorrowRecord.objects.filter(user=request.user).select_related('book')
    context = {
        'records': records,
        'active_count': records.filter(status='borrowed').count(),
    }
    return render(request, 'library/my_books.html', context)


# ============================================================
# AUTHENTICATION & AUTHORIZATION
# ============================================================

def register_view(request):
    """
    User registration - demonstrates form handling, user creation,
    automatic login after registration, and cookie/session setup.
    """
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your account has been created.')
            return redirect('home')
    else:
        form = UserRegistrationForm()

    return render(request, 'library/register.html', {'form': form})


def login_view(request):
    """
    Login view - demonstrates authentication, cookie setting, and sessions.
    """
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember_me')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)

            # Session/Cookie handling: remember me functionality
            if not remember_me:
                request.session.set_expiry(0)  # Session expires when browser closes
            else:
                request.session.set_expiry(1209600)  # 2 weeks

            messages.success(request, f'Welcome back, {user.username}!')
            return redirect(request.GET.get('next', 'home'))
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'library/login.html')


def logout_view(request):
    """Logout view - clears session data."""
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


# ============================================================
# API ENDPOINT (JSON Response)
# ============================================================

def api_books(request):
    """
    JSON API endpoint - demonstrates returning different response types.
    """
    books = Book.objects.select_related('category').all()
    data = {
        'total': books.count(),
        'books': [
            {
                'id': b.id,
                'title': b.title,
                'author': b.author,
                'isbn': b.isbn,
                'category': b.category.name,
                'available': b.is_available,
                'copies': b.copies_available,
            }
            for b in books
        ]
    }
    return JsonResponse(data)


# ============================================================
# ACTIVITY LOG (Middleware data display)
# ============================================================

@login_required
def activity_log(request):
    """
    Shows recent activity from the logging middleware.
    Demonstrates: How middleware-captured data can be displayed.
    """
    logs = ActivityLog.objects.all()[:50]
    return render(request, 'library/activity_log.html', {'logs': logs})
