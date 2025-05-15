from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
import re
from rest_framework.response import Response
from api.models import Expense

def handle_total_query(query, expenses):
    """Handle queries about total spending"""
    is_this_month = "this month" in query or "current month" in query
    is_last_month = "last month" in query or "previous month" in query

    if is_this_month:
        today = timezone.now().date()
        start_of_month = today.replace(day=1)
        result = expenses.filter(date__gte=start_of_month).aggregate(total=Sum("amount"))
        return Response({
            "response": f"This month, you've spent ₹{result['total'] or 0:.2f}."
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
            "response": f"Last month, you spent ₹{result['total'] or 0:.2f}."
        })
    else:
        result = expenses.aggregate(total=Sum("amount"))
        return Response({
            "response": f"In total, you've spent ₹{result['total'] or 0:.2f}."
        })

def handle_highest_query(query, expenses):
    """Handle queries about the highest expenses"""
    if "category" in query:
        category_totals = expenses.values("category").annotate(total=Sum("amount")).order_by("-total")
        if category_totals:
            top_category = category_totals[0]
            return Response({
                "response": f"Your highest spending category is {top_category['category']} with a total of ₹{top_category['total']:.2f}."
            })
    else:
        highest_expense = expenses.order_by("-amount").first()
        return Response({
            "response": f"Your highest expense is ₹{highest_expense.amount} for {highest_expense.description} on {highest_expense.date} in the {highest_expense.category} category."
        })

def handle_average_query(query, expenses):
    """Handle queries about average spending"""
    categories = list(set(expenses.values_list("category", flat=True)))
    mentioned_category = next((cat for cat in categories if cat.lower() in query), None)

    if mentioned_category:
        category_expenses = expenses.filter(category=mentioned_category)
        result = category_expenses.aggregate(avg=Sum("amount") / Count("id"))
        return Response({
            "response": f"Your average expense in the {mentioned_category} category is ₹{result['avg'] or 0:.2f}."
        })
    else:
        result = expenses.aggregate(avg=Sum("amount") / Count("id"))
        return Response({
            "response": f"Your average expense amount is ₹{result['avg'] or 0:.2f}."
        })

def handle_categories_query(expenses):
    """List all categories with their totals"""
    category_totals = expenses.values("category").annotate(total=Sum("amount")).order_by("-total")
    
    if not category_totals:
        return Response({"response": "You don't have any categorized expenses yet."})

    response = "Here are your expense categories:\n\n"
    for idx, cat in enumerate(category_totals, 1):
        response += f"{idx}. {cat['category']}: ₹{cat['total']:.2f}\n"
    
    return Response({"response": response})

def handle_recent_query(query, expenses):
    """Get recent expenses"""
    limit = 5  # Default number to show
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

def get_predictions(request):
    """Handle prediction queries (implement your own logic here)"""
    return Response({
        "response": "This functionality is not yet implemented. Please check back later."
    })
