from rest_framework import viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from datetime import datetime, timedelta
from django.utils import timezone
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from dateutil.relativedelta import relativedelta
from django.db.models import Count
from rest_framework.decorators import action
from django.http import HttpResponse
from .models import Expense, Category, Budget, FinancialGoal
from .serializers import (
    ExpenseSerializer,
    CategorySerializer,
    UserSerializer,
    RegisterSerializer,
    BudgetSerializer,
    FinancialGoalSerializer,
)
import re
import csv
from io import StringIO, BytesIO
import json
from django.template.loader import get_template
from django.template import Context
from decimal import Decimal, InvalidOperation
from api.utils import (handle_expense_forecast, 
    handle_total_spending, 
    handle_highest_expense,
    handle_recent_expenses, 
    handle_category_spending, 
    handle_categories_query,
    handle_savings_progress, 
    handle_budget_progress)
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User

@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def request_password_reset(request):
    """Request a password reset link"""
    email = request.data.get("email")
    
    if not email:
        return Response(
            {"error": "Email is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    
    try:
        user = User.objects.get(email=email)
        
        # Generate token and uid
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        # Create reset link
        # In a real app, this should point to your frontend URL
        reset_link = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}/"
        
        # Send email
        subject = "Password Reset for Your Expense Tracker"
        message = f"""
        Hello {user.username},
        
        You requested a password reset for your Expense Tracker account.
        
        Please click the link below to reset your password:
        {reset_link}
        
        If you didn't request this, please ignore this email.
        
        Thanks,
        The Expense Tracker Team
        """
        
        from_email = settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@expensetracker.com'
        
        send_mail(
            subject,
            message,
            from_email,
            [user.email],
            fail_silently=False,
        )
        
        return Response(
            {"message": "Password reset email has been sent."},
            status=status.HTTP_200_OK,
        )
    except User.DoesNotExist:
        # Don't reveal whether a user exists to prevent user enumeration
        return Response(
            {"message": "Password reset email has been sent if the email is valid."},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def validate_password_reset_token(request):
    """Validate password reset token"""
    uid = request.data.get("uid")
    token = request.data.get("token")
    
    if not uid or not token:
        return Response(
            {"error": "Both UID and token are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    
    try:
        # Decode the UID to get the User
        uid = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=uid)
        
        # Check if the token is valid
        if default_token_generator.check_token(user, token):
            return Response(
                {"valid": True, "uid": uid, "token": token},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"valid": False, "error": "Invalid or expired token"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response(
            {"valid": False, "error": "Invalid user ID"},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def reset_password(request):
    """Reset password with valid token"""
    uid = request.data.get("uid")
    token = request.data.get("token")
    new_password = request.data.get("new_password")
    
    if not uid or not token or not new_password:
        return Response(
            {"error": "UID, token, and new password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    
    # Password validation
    if len(new_password) < 8:
        return Response(
            {"error": "Password must be at least 8 characters long"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    
    try:
        # Decode the UID to get the User
        uid = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=uid)
        
        # Check if the token is valid
        if default_token_generator.check_token(user, token):
            # Set the new password
            user.set_password(new_password)
            user.save()
            
            # Invalidate all existing tokens for the user
            Token.objects.filter(user=user).delete()
            new_token = Token.objects.create(user=user)
            
            return Response(
                {
                    "message": "Password has been reset successfully",
                    "token": new_token.key,
                    "user": UserSerializer(user).data,
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": "Invalid or expired token"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response(
            {"error": "Invalid user ID"},
            status=status.HTTP_400_BAD_REQUEST,
        )

# Authentication views
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def register_user(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        token, created = Token.objects.get_or_create(user=user)
        return Response(
            {"token": token.key, "user": UserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def login_user(request):
    username = request.data.get("username")
    password = request.data.get("password")

    user = authenticate(username=username, password=password)
    if user:
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        token, created = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})
    return Response(
        {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
    )

@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def update_email(request):
    user = request.user
    new_email = request.data.get("new_email")

    if not new_email:
        return Response(
            {"error": "New email is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate the new email
    if not re.match(r"[^@]+@[^@]+\.[^@]+", new_email):
        return Response(
            {"error": "Invalid email format"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check if the new email is the same as the current one
    if new_email == user.email:
        return Response(
            {"error": "New email is the same as the current email"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Update the user's email
    user.email = new_email
    user.save()

    # Optionally, you can also generate a new token if needed
    Token.objects.filter(user=user).delete()
    token = Token.objects.create(user=user)

    return Response(
        {"message": "Email updated successfully", "token": token.key}
    )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_user_profile(request):
    user = request.user
    return Response(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "date_joined": user.date_joined,
            "last_login": user.last_login,
        }
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    user = request.user
    current_password = request.data.get("current_password")
    new_password = request.data.get("new_password")

    if not current_password or not new_password:
        return Response(
            {"error": "Both current and new password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Verify current password
    if not user.check_password(current_password):
        return Response(
            {"error": "Current password is incorrect"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Set new password
    user.set_password(new_password)
    user.save()

    # Generate new token
    Token.objects.filter(user=user).delete()
    token = Token.objects.create(user=user)

    return Response({"message": "Password changed successfully", "token": token.key})


# Expense viewset
class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Expense.objects.filter(user=self.request.user)


# Category viewset
class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)
    
class BudgetViewSet(viewsets.ModelViewSet):
    serializer_class = BudgetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Budget.objects.filter(user=self.request.user)
    
    def list(self, request, *args, **kwargs):
        """Override list method to include spending data"""
        queryset = self.get_queryset()
        
        # Get current month for expense calculations
        today = timezone.now().date()
        start_of_month = today.replace(day=1)
        
        # Prepare enhanced budget data
        budget_data = []
        
        for budget in queryset:
            # Calculate current month's spending for this category
            current_month_spending = Expense.objects.filter(
                user=request.user,
                category=budget.category.name,
                date__gte=start_of_month
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            # Calculate total spending for this category (all time)
            total_category_spending = Expense.objects.filter(
                user=request.user,
                category=budget.category.name
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            # Calculate percentage and remaining amount
            percentage = (current_month_spending / budget.limit) * 100 if budget.limit > 0 else 0
            remaining = budget.limit - current_month_spending
            
            # Create the enhanced budget object
            budget_data.append({
                'id': budget.id,
                'category': budget.category.id,
                'category_name': budget.category.name,
                'limit': budget.limit,
                'spent': current_month_spending,
                'total_spent': total_category_spending,
                'percentage': round(percentage, 1),
                'remaining': remaining
            })
        
        return Response(budget_data)
    
    def create(self, request, *args, **kwargs):
        """Create a new budget, handling the category relationship"""
        category_id = request.data.get('category')
        limit = request.data.get('limit')
        
        if not category_id or limit is None:
            return Response(
                {'error': 'Category and limit are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Convert limit to float and validate
            limit = float(limit)
            if limit < 0:
                return Response(
                    {'error': 'Limit must be a positive number'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            # Get the category
            category = Category.objects.get(id=category_id, user=request.user)
            
            # Check if budget already exists for this category
            existing_budget = Budget.objects.filter(
                user=request.user,
                category=category
            ).first()
            
            if existing_budget:
                # Update existing budget
                existing_budget.limit = limit
                existing_budget.save()
                serializer = self.get_serializer(existing_budget)
                return Response(serializer.data)
            
            # Create new budget
            budget = Budget.objects.create(
                user=request.user,
                category=category,
                limit=limit
            )
            
            serializer = self.get_serializer(budget)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Category.DoesNotExist:
            return Response(
                {'error': 'Category not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {'error': 'Limit must be a valid number'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )

class FinancialGoalViewSet(viewsets.ModelViewSet):
    serializer_class = FinancialGoalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return FinancialGoal.objects.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def update_contribution(self, request, pk=None):
        """Add contribution to a financial goal"""
        try:
            goal = self.get_object()
            amount = request.data.get('amount', 0)
            
            try:
                amount = Decimal(amount)
                if amount <= 0:
                    return Response(
                        {"error": "Amount must be a positive number"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except (InvalidOperation, TypeError):
                return Response(
                    {"error": "Amount must be a valid decimal number"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            goal.currentAmount += amount
            goal.save()
            
            return Response(self.get_serializer(goal).data)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


# AI Prediction view
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_predictions(request):
    # Get all expenses for the user
    expenses = Expense.objects.filter(user=request.user)

    if not expenses.exists():
        return Response([])

    # Get unique categories
    categories = set(expenses.values_list("category", flat=True))

    # Prepare response data
    predictions = []

    for category in categories:
        category_expenses = expenses.filter(category=category)

        # Skip if not enough data
        if category_expenses.count() < 3:
            continue

        # Convert to DataFrame for easier manipulation
        df = pd.DataFrame(list(category_expenses.values("date", "amount")))
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M")

        # Group by month and sum amounts
        monthly_data = df.groupby("month")["amount"].sum().reset_index()
        monthly_data["month_num"] = range(1, len(monthly_data) + 1)

        # Need at least 3 months of data for meaningful prediction
        if len(monthly_data) < 3:
            continue

        # Prepare data for regression
        X = monthly_data[["month_num"]].values
        y = monthly_data["amount"].values

        # Train linear regression model
        model = LinearRegression()
        model.fit(X, y)

        # Predict next 3 months
        next_months = []
        last_month = monthly_data["month"].iloc[-1]

        for i in range(1, 4):
            next_month_num = len(monthly_data) + i
            predicted_amount = model.predict([[next_month_num]])[0]

            # Ensure prediction is not negative
            predicted_amount = max(0, predicted_amount)

            # Format month for display
            next_month_date = last_month.to_timestamp() + relativedelta(months=i)
            month_str = next_month_date.strftime("%b %Y")

            next_months.append(
                {
                    "month": month_str,
                    "predicted_amount": round(float(predicted_amount), 2),
                }
            )
        existing_entry = next(
            (item for item in predictions if item["category"] == category), None
        )
        if not existing_entry:
            predictions.append({"category": category, "predictions": next_months})

    return Response(predictions)


# Automated categorization
def suggest_category(description, user):
    """Suggest a category based on expense description"""
    # Get all expenses with categories
    expenses = Expense.objects.filter(user=user)

    if not expenses.exists():
        return None

    # Simple keyword matching for now
    description = description.lower()

    # Check for exact matches first
    exact_matches = expenses.filter(description__iexact=description)
    if exact_matches.exists():
        # Return the most common category for this exact description
        return (
            exact_matches.values("category")
            .annotate(count=Count("category"))
            .order_by("-count")
            .first()["category"]
        )

    # Check for partial matches
    for word in description.split():
        if len(word) > 3:  # Only consider words with more than 3 characters
            partial_matches = expenses.filter(description__icontains=word)
            if partial_matches.exists():
                # Return the most common category for this partial match
                return (
                    partial_matches.values("category")
                    .annotate(count=Count("category"))
                    .order_by("-count")
                    .first()["category"]
                )

    # If no matches, return the most common category overall
    return (
        expenses.values("category")
        .annotate(count=Count("category"))
        .order_by("-count")
        .first()["category"]
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def suggest_category_api(request):
    description = request.data.get("description", "")
    if not description:
        return Response(
            {"error": "Description is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    category = suggest_category(description, request.user)
    return Response({"suggested_category": category})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_csv(request):
    """Export user expenses as CSV"""
    user = request.user
    expenses = Expense.objects.filter(user=user).order_by('-date')
    
    # Create a file-like buffer to receive CSV data
    csv_buffer = StringIO()
    writer = csv.writer(csv_buffer)
    
    # Add CSV header
    writer.writerow(['Date', 'Description', 'Category', 'Amount'])
    
    # Add expense data
    for expense in expenses:
        writer.writerow([
            expense.date.strftime('%Y-%m-%d'),
            expense.description,
            expense.category,
            expense.amount
        ])
    
    # Create response with CSV content
    response = HttpResponse(csv_buffer.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="expenses.csv"'
    
    return response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_data(request, format_type):
    """Unified export endpoint supporting multiple formats"""
    if format_type.lower() == 'csv':
        return export_csv(request)
    else:
        return HttpResponse(
            json.dumps({"error": f"Unsupported format: {format_type}"}),
            content_type='application/json',
            status=400
        )

def detect_intent(task_classifier,candidate_labels,query):
    result = task_classifier(query, candidate_labels)
    return result["labels"][0]

@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def chatbot_query(request):
    """Process natural language queries about expenses"""
    query = request.data.get("query", "").lower()
    user = request.user
    # classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
    # labels = [
    # "total_spending",
    # "category_spending",
    # "recent_expenses",
    # "highest_expense",
    # "forecast_expenses",
    # "budgeting_goal",
    # "savings_progress",
    # "general_greeting",
    # "help",
    # "random"
    # ]
    # result = classifier(query, labels)
    # intent = result["labels"][0]
    # top_score = result["scores"][0]
    # THRESHOLD = 0.4
    # if top_score < THRESHOLD:
    #     intent = "unknown"
    clean_query = ''.join(c for c in query if c.isalnum() or c.isspace())
    
    # Simple rule-based intent detection
    def detect_intent(query):
        # Add question marks to account for both forms in the original code
        if any(greeting in query for greeting in greetings):
            return "general_greeting"
            
        if any(question in query for question in general_questions) or "help" in query:
            return "help"
            
        if ("total" in query or "spent" in query or "spending" in query or "how much" in query):
            return "total_spending"
            
        if "category" in query or "categories" in query:
            return "category_spending"
            
        if "recent" in query or "latest" in query or "last" in query:
            return "recent_expenses"
            
        if "highest" in query or "most" in query or "top" in query or "biggest" in query:
            return "highest_expense"
            
        if "budget" in query or "limit" in query:
            return "budgeting_goal"
            
        if "save" in query or "saving" in query or "savings" in query or "goal" in query:
            return "savings_progress"
            
        if "predict" in query or "forecast" in query or "future" in query or "next month" in query:
            return "forecast_expenses"
            
        return "unknown"
    
    # Get user's intent
    intent = detect_intent(clean_query)
    if not expenses.exists() and intent not in ["general_greeting", "help"]:
        return Response({"response": "You don't have any expenses recorded yet."})
    # Greetings and general questions
    greetings = [
    "hi", "hi?", "hello", "hello?", "hey", "hey?", "what's up", "what's up?", 
    "how are you", "how are you?", "yo", "yo?", "good morning", "good morning?", 
    "good afternoon", "good afternoon?", "good evening", "good evening?", 
    "sup", "sup?", "hey there", "hey there?", "hiya", "hiya?", "howdy", "howdy?", 
    "what's good", "what's good?", "what's happening", "what's happening?", 
    "how's it going", "how's it going?", "what's new", "what's new?"
    ]

    general_questions = [
    "who are you", "who are you?", "what can you do", "what can you do?", "help", "help?", 
    "what do you do", "what do you do?", "tell me about yourself", "tell me about yourself?", 
    "what are your skills", "what are your skills?", "how can you help me", "how can you help me?", 
    "what services do you offer", "what services do you offer?", "what are you capable of", 
    "what are you capable of?", "what's your purpose", "what's your purpose?", "what do you know", 
    "what do you know?", "what can you tell me", "what can you tell me?", "how do you work", 
    "how do you work?", "what's your function", "what's your function?", "what can you help me with", 
    "what can you help me with?", "how can i use you", "how can i use you?", "what's your job", 
    "what's your job?", "what are your features", "what are your features?"
    ]

    if query in greetings:
        return Response({"response": "Hello! How can I assist you with your expenses today?"})
    elif query.lower() in general_questions or "help" in query.lower():
        response = (
            "I'm a chatbot that can help you with queries about your expenses.\n\n"
            "I can help you with queries like:\n\n"
            "• How much have I spent this month?\n"
            "• What's my total spending on food?\n"
            "• What are my top spending categories?\n"
            "• What's my highest expense?\n"
            "• Show me my recent expenses.\n"
            "• Predict my future expenses."
        )
        return Response({"response": response})
    
    # Get all user expenses
    expenses = Expense.objects.filter(user=user)
    
    if not expenses.exists():
        return Response({"response": "You don't have any expenses recorded yet."})
    
    # Process different types of queries
    if "total" in query or "spent" in query:
        # Handle queries about total spending
        
        # Check if query is about a specific category
        categories = list(set(expenses.values_list("category", flat=True)))
        mentioned_category = next((cat for cat in categories if cat.lower() in query), None)
        
        # Check if query is about a specific time period
        is_this_month = "this month" in query or "current month" in query
        is_last_month = "last month" in query or "previous month" in query
        
        if mentioned_category:
            category_expenses = expenses.filter(category=mentioned_category)
            
            if is_this_month:
                today = timezone.now().date()
                start_of_month = today.replace(day=1)
                result = category_expenses.filter(date__gte=start_of_month).aggregate(total=Sum("amount"))
                return Response({
                    "response": f"This month, you've spent ₹{result['total'] or 0:.2f} on {mentioned_category}."
                })
            elif is_last_month:
                today = timezone.now().date()
                start_of_this_month = today.replace(day=1)
                last_month = start_of_this_month - timedelta(days=1)
                start_of_last_month = last_month.replace(day=1)
                result = category_expenses.filter(
                    date__gte=start_of_last_month, 
                    date__lt=start_of_this_month
                ).aggregate(total=Sum("amount"))
                return Response({
                    "response": f"Last month, you spent ₹{result['total'] or 0:.2f} on {mentioned_category}."
                })
            else:
                # All time for this category
                result = category_expenses.aggregate(total=Sum("amount"))
                return Response({
                    "response": f"In total, you've spent ₹{result['total'] or 0:.2f} on {mentioned_category}."
                })
        else:
            # Total spending without category filter
            if is_this_month:
                today = timezone.now().date()
                start_of_month = today.replace(day=1)
                result = expenses.filter(date__gte=start_of_month).aggregate(total=Sum("amount"))
                return Response({
                    "response": f"This month, you've spent a total of ₹{result['total'] or 0:.2f}."
                })
            elif is_last_month:
                today = timezone.now().date()
                start_of_this_month = today.replace(day=1)
                last_month = start_of_this_month - timedelta(days=1)
                start_of_last_month = last_month.replace(day=1)
                result = expenses.filter(
                    date__gte=start_of_last_month, 
                    date__lt=start_of_this_month
                ).aggregate(total=Sum("amount"))
                return Response({
                    "response": f"Last month, you spent a total of ₹{result['total'] or 0:.2f}."
                })
            else:
                # All time total
                result = expenses.aggregate(total=Sum("amount"))
                return Response({
                    "response": f"In total, you've spent ₹{result['total'] or 0:.2f} across all categories."
                })
    
    elif "highest" in query or "most" in query or "top" in query:
        # Handle queries about highest expenses
        
        # Check if it's about categories or individual expenses
        if "category" in query:
            # Get the category with highest total
            category_totals = expenses.values("category").annotate(total=Sum("amount")).order_by("-total")
            if category_totals:
                top_category = category_totals[0]
                return Response({
                    "response": f"Your highest spending category is {top_category['category']} with a total of ₹{top_category['total']:.2f}."
                })
        else:
            # Get the highest individual expense
            highest_expense = expenses.order_by("-amount").first()
            return Response({
                "response": f"Your highest expense is ₹{highest_expense.amount} for {highest_expense.description} on {highest_expense.date} in the {highest_expense.category} category."
            })
    
    elif "average" in query or "avg" in query:
        # Handle queries about average spending
        
        # Check if query is about a specific category
        categories = list(set(expenses.values_list("category", flat=True)))
        mentioned_category = next((cat for cat in categories if cat.lower() in query), None)
        
        if mentioned_category:
            # Average for specific category
            category_expenses = expenses.filter(category=mentioned_category)
            result = category_expenses.aggregate(avg=Sum("amount") / Count("id"))
            return Response({
                "response": f"Your average expense in the {mentioned_category} category is ₹{result['avg'] or 0:.2f}."
            })
        else:
            # Overall average
            result = expenses.aggregate(avg=Sum("amount") / Count("id"))
            return Response({
                "response": f"Your average expense amount is ₹{result['avg'] or 0:.2f}."
            })
    
    elif "categories" in query or "category" in query:
        # List all categories with their totals
        category_totals = expenses.values("category").annotate(total=Sum("amount")).order_by("-total")
        
        if not category_totals:
            return Response({"response": "You don't have any categorized expenses yet."})
        
        response = "Here are your expense categories:\n\n"
        for idx, cat in enumerate(category_totals, 1):
            response += f"{idx}. {cat['category']}: ₹{cat['total']:.2f}\n"
        
        return Response({"response": response})
    
    elif "recent" in query or "latest" in query or "last" in query:
        # Get recent expenses
        limit = 5  # Default number to show
        
        # Check if a specific number is mentioned
        import re
        num_match = re.search(r'\b(\d+)\b', query)
        if num_match:
            limit = int(num_match.group(1))
        
        recent = expenses.order_by("-date")[:limit]
        
        if not recent:
            return Response({"response": "You don't have any recent expenses."})
        
        response = f"Here are your {limit} most recent expenses:\n\n"
        for idx, exp in enumerate(recent, 1):
            response += f"{idx}. {exp.description}: ₹{exp.amount} ({exp.date}) - {exp.category}\n"
        
        return Response({"response": response})
    
    elif "predict" in query or "forecast" in query or "future" in query:
        # Redirect to predictions
        categories = list(set(expenses.values_list("category", flat=True)))
        mentioned_category = next((cat for cat in categories if cat.lower() in query), None)
        
        if mentioned_category:
            response = f"Based on your spending patterns, here's a prediction for {mentioned_category}. You can view detailed predictions in the Predictions section of the dashboard."
        else:
            response = "You can view detailed spending predictions for all categories in the Predictions section of the dashboard."
        
        return Response({"response": response})
    
    if intent == "total_spending":
        return handle_total_spending(user)
    elif intent == "category_spending":
        return handle_category_spending(user)
    elif intent == "recent_expenses":
        return handle_recent_expenses(user)
    elif intent == "highest_expense":
        return handle_highest_expense(user)
    elif intent == "budgeting_goal":
        return handle_budget_progress(user)
    elif intent == "savings_progress":
        return handle_savings_progress(user)
    elif intent == "forecast_expenses":
        return handle_expense_forecast(user)
    elif intent == "general_greeting":
        return Response({"response": "Hello! How can I help with your expenses today?"})
    elif intent == "help":
        return Response({"response": "I can show spending summaries, recent transactions, budgeting goals, and predictions."})
    else:
        # Handle unknown queries
        response = (
            "I'm not sure how to answer that question about your expenses. "
            "Try asking about your total spending, spending by category, or highest expenses. "
            "Type 'help' to see what I can do."
        )
        return Response({"response": response}) 