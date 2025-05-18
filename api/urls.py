from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"expenses", views.ExpenseViewSet, basename="expense")
router.register(r"categories", views.CategoryViewSet, basename="category")
router.register(r"budgets", views.BudgetViewSet, basename="budget")
router.register(r"goals", views.FinancialGoalViewSet, basename="goal")

urlpatterns = [
    path("", include(router.urls)),
    path("auth/register/", views.register_user, name="register"),
    path("auth/login/", views.login_user, name="login"),
    path("auth/profile/", views.get_user_profile, name="profile"),
    path("auth/change-password/", views.change_password, name="change-password"),
    path("predictions/", views.get_predictions, name="predictions"),
    path("suggest-category/", views.suggest_category_api, name="suggest-category"),
    path("chatbot/", views.chatbot_query, name="chatbot"),
    path("export/csv/", views.export_csv, name="export-csv"),
    path("export/<str:format_type>/", views.export_data, name="export-data"),
    path('auth/update-email/', views.update_email, name='update-email'),
    path('password-reset/request/', views.request_password_reset, name='password-reset-request'),
    path('password-reset/validate-token/', views.validate_password_reset_token, name='validate-reset-token'),
    path('password-reset/reset/', views.reset_password, name='password-reset'),
]
