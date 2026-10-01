import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth import get_user_model
from claims.models import Claim
from analysis.models import Analysis

User = get_user_model()


class Command(BaseCommand):
    help = "Seed database with admin, sample users, claims, and analysis results."

    def add_arguments(self, parser):
        parser.add_argument(
            "--admin-email",
            type=str,
            help="Admin user email",
            default="admin@infotrust.local"
        )
        parser.add_argument(
            "--admin-password",
            type=str,
            help="Admin user password",
        )

    def handle(self, *args, **options):
        admin_email = os.environ.get("SEED_ADMIN_EMAIL", options["admin_email"])
        admin_password = options.get("admin_password") or os.environ.get("SEED_ADMIN_PASSWORD")

        if not admin_password:
            raise CommandError("Admin password must be provided via --admin-password or SEED_ADMIN_PASSWORD env var.")

        with transaction.atomic():
            # 1. Create or verify Admin
            admin_user = User.objects.filter(email=admin_email).first()
            if not admin_user:
                self.stdout.write(f"Creating admin user {admin_email}...")
                admin_user = User.objects.create_superuser(
                    email=admin_email,
                    full_name="Admin User",
                    password=admin_password
                )
            else:
                if not admin_user.is_superuser or admin_user.role != "ADMIN":
                    raise CommandError(f"User {admin_email} exists but is not an admin/superuser.")
                self.stdout.write(f"Admin user {admin_email} already exists and is valid. Reusing.")

            # 2. Create Sample Users (with unusable passwords)
            sample_users_data = [
                {"email": "user1@infotrust.local", "full_name": "Sample User One"},
                {"email": "user2@infotrust.local", "full_name": "Sample User Two"},
            ]
            
            sample_users = []
            for udata in sample_users_data:
                user = User.objects.filter(email=udata["email"]).first()
                if not user:
                    self.stdout.write(f"Creating sample user {udata['email']}...")
                    user = User.objects.create_user(
                        email=udata["email"],
                        full_name=udata["full_name"],
                        password=None
                    )
                else:
                    self.stdout.write(f"Sample user {udata['email']} already exists. Reusing.")
                sample_users.append(user)

            user1, user2 = sample_users

            # 3. Create Sample Claims & Analyses
            # We need 6 claims: 3 COMPLETED (with analysis), 3 non-COMPLETED (no analysis).
            
            completed_claims_data = [
                {
                    "user": user1,
                    "text": "Seed Claim 1 (Credible): Drinking water hydrates you.",
                    "verdict": "CREDIBLE",
                    "score": 95.0,
                    "summary": "Hydration is a scientifically proven fact."
                },
                {
                    "user": user1,
                    "text": "Seed Claim 2 (Uncertain): Drinking 8 glasses of water a day is mandatory for everyone.",
                    "verdict": "UNCERTAIN",
                    "score": 50.0,
                    "summary": "The exact amount of water needed varies by individual."
                },
                {
                    "user": user2,
                    "text": "Seed Claim 3 (Misinformation): Drinking water cures all diseases.",
                    "verdict": "MISINFORMATION",
                    "score": 10.0,
                    "summary": "Water is essential but does not cure diseases."
                }
            ]

            non_completed_claims_data = [
                {
                    "user": user1,
                    "text": "Seed Claim 4 (Pending): The sky is blue because of the ocean.",
                    "status": "PENDING"
                },
                {
                    "user": user2,
                    "text": "Seed Claim 5 (Processing): Eating carrots improves night vision significantly.",
                    "status": "PROCESSING"
                },
                {
                    "user": user2,
                    "text": "Seed Claim 6 (Failed): Bananas grow on trees.",
                    "status": "FAILED"
                }
            ]

            # Generate COMPLETED claims and Analyses
            for cdata in completed_claims_data:
                claim, created = Claim.objects.get_or_create(
                    user=cdata["user"],
                    text=cdata["text"],
                    defaults={"status": "COMPLETED"}
                )
                if created:
                    self.stdout.write(f"Created completed claim: {cdata['text']}")
                else:
                    self.stdout.write(f"Reused completed claim: {cdata['text']}")

                analysis, a_created = Analysis.objects.get_or_create(
                    claim=claim,
                    defaults={
                        "verdict": cdata["verdict"],
                        "credibility_score": cdata["score"],
                        "final_weighted_score": cdata["score"],
                        "explainability_json": {"reasons": [cdata["summary"]]},
                        "model_prediction": cdata["verdict"],
                        "model_confidence": 0.9,
                        "fact_check_summary": cdata["summary"],
                        "fact_check_match_count": 1,
                        "narrative_match_count": 0,
                        "highest_similarity_score": 0.9,
                        "rule_based_flags": []
                    }
                )
                if a_created:
                    self.stdout.write(f"Created analysis for claim: {cdata['text']}")
                else:
                    self.stdout.write(f"Reused analysis for claim: {cdata['text']}")

            # Generate non-COMPLETED claims
            for ncdata in non_completed_claims_data:
                claim, created = Claim.objects.get_or_create(
                    user=ncdata["user"],
                    text=ncdata["text"],
                    defaults={"status": ncdata["status"]}
                )
                if created:
                    self.stdout.write(f"Created non-completed claim: {ncdata['text']}")
                else:
                    self.stdout.write(f"Reused non-completed claim: {ncdata['text']}")

            self.stdout.write(self.style.SUCCESS("Successfully seeded the database!"))
