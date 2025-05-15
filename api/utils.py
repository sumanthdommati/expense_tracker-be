from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
import re
from rest_framework.response import Response
from api.models import Expense, Budget,FinancialGoal

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

def handle_total_spending(user):
    total = Expense.objects.filter(user=user).aggregate(total=Sum("amount"))["total"] or 0
    return Response({"response": f"You've spent a total of ₹{total:.2f}."})

def handle_category_spending(user):
    category_totals = Expense.objects.filter(user=user).values("category").annotate(total=Sum("amount")).order_by("-total")
    if not category_totals:
        return Response({"response": "You haven't recorded any category-wise expenses yet."})
    
    response = "Here's your spending by category:\n\n"
    for cat in category_totals:
        response += f"- {cat['category']}: ₹{cat['total']:.2f}\n"
    return Response({"response": response.strip()})

def handle_recent_expenses(user, limit=5):
    recent = Expense.objects.filter(user=user).order_by("-date")[:limit]
    if not recent:
        return Response({"response": "No recent expenses found."})
    
    response = "Here are your most recent expenses:\n\n"
    for exp in recent:
        response += f"- {exp.description}: ₹{exp.amount} on {exp.date} ({exp.category})\n"
    return Response({"response": response.strip()})

def handle_highest_expense(user):
    highest = Expense.objects.filter(user=user).order_by("-amount").first()
    if not highest:
        return Response({"response": "You don't have any recorded expenses yet."})
    
    return Response({
        "response": f"Your highest expense is ₹{highest.amount} for '{highest.description}' on {highest.date} in category {highest.category}."
    })

def handle_budget_progress(user):
    budgets = Budget.objects.filter(user=user)
    if not budgets.exists():
        return Response({"response": "You haven't set up any budgets yet."})
    
    response = "Here's your budget progress:\n\n"
    for budget in budgets:
        spent = Expense.objects.filter(user=user, category=budget.category.name).aggregate(total=Sum("amount"))["total"] or 0
        response += (
            f"- {budget.category.name}: ₹{spent:.2f} / ₹{budget.limit:.2f} "
            f"({(spent / budget.limit * 100) if budget.limit > 0 else 0:.1f}%)\n"
        )
    return Response({"response": response.strip()})

def handle_savings_progress(user):
    goals = FinancialGoal.objects.filter(user=user)
    if not goals.exists():
        return Response({"response": "You don't have any financial goals set yet."})
    
    response = "Here's your savings goal progress:\n\n"
    for goal in goals:
        percent = (goal.currentAmount / goal.targetAmount * 100) if goal.targetAmount > 0 else 0
        response += f"- {goal.name}: ₹{goal.currentAmount:.2f} / ₹{goal.targetAmount:.2f} ({percent:.1f}%)\n"
    return Response({"response": response.strip()})

def handle_expense_forecast(user):
    # Simplified logic: monthly average multiplied by 12
    from django.db.models.functions import TruncMonth
    expenses = Expense.objects.filter(user=user)
    
    if not expenses.exists():
        return Response({"response": "No expenses found to forecast from."})
    
    monthly = expenses.annotate(month=TruncMonth("date")).values("month").annotate(total=Sum("amount"))
    avg_monthly = sum(month["total"] for month in monthly) / len(monthly)
    
    return Response({"response": f"Based on your average monthly spending, you may spend approximately ₹{avg_monthly * 12:.2f} this year."})