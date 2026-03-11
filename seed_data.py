"""
Seed script: Creates initial badges and internship data.
Run: python seed_data.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.core.database import AsyncSessionLocal, init_db
# Import ALL models so SQLAlchemy relationship registry is fully populated
import app.models.user        # noqa: F401
import app.models.roadmap     # noqa: F401
import app.models.chat        # noqa: F401
import app.models.analytics   # noqa: F401
import app.models.gamification  # noqa: F401
import app.models.project     # noqa: F401
from app.models.gamification import Badge
from app.models.project import Internship
from sqlalchemy import select


BADGES = [
    {"name": "First Step", "description": "Complete your first learning step", "icon": "footprints", "condition_type": "steps_completed", "condition_value": 1},
    {"name": "Getting Started", "description": "Complete 5 learning steps", "icon": "rocket", "condition_type": "steps_completed", "condition_value": 5},
    {"name": "Week Warrior", "description": "Maintain a 7-day learning streak", "icon": "flame", "condition_type": "streak", "condition_value": 7},
    {"name": "Code Master", "description": "Complete 20 learning steps", "icon": "code", "condition_type": "steps_completed", "condition_value": 20},
    {"name": "Consistency King", "description": "Maintain a 30-day learning streak", "icon": "crown", "condition_type": "streak", "condition_value": 30},
    {"name": "Halfway There", "description": "Complete 10 learning steps", "icon": "target", "condition_type": "steps_completed", "condition_value": 10},
]

INTERNSHIPS = [
    {"title": "Frontend Developer Intern", "company": "TechStartup Inc.", "domain": "Web Development", "location": "Remote", "level": "Beginner", "description": "Work on React-based UI components for our SaaS platform.", "required_skills": '["HTML", "CSS", "JavaScript", "React"]', "apply_url": None},
    {"title": "Full Stack Developer Intern", "company": "BuildCo", "domain": "Web Development", "location": "Bangalore, India", "level": "Intermediate", "description": "Build APIs and React frontends for our e-commerce platform.", "required_skills": '["React", "Node.js", "PostgreSQL"]', "apply_url": None},
    {"title": "Data Science Intern", "company": "DataDriven ML", "domain": "Data Science", "location": "Remote", "level": "Beginner", "description": "Analyze datasets and build ML models using Python.", "required_skills": '["Python", "Pandas", "NumPy", "Matplotlib"]', "apply_url": None},
    {"title": "ML Engineer Intern", "company": "AI Labs", "domain": "Machine Learning", "location": "Hyderabad, India", "level": "Intermediate", "description": "Train and deploy ML models using PyTorch and FastAPI.", "required_skills": '["Python", "PyTorch", "FastAPI", "Docker"]', "apply_url": None},
    {"title": "Backend Developer Intern", "company": "ScaleUp Tech", "domain": "Backend Development", "location": "Remote", "level": "Beginner", "description": "Build REST APIs with FastAPI and PostgreSQL.", "required_skills": '["Python", "FastAPI", "PostgreSQL", "REST"]', "apply_url": None},
    {"title": "Cloud DevOps Intern", "company": "CloudNative Co.", "domain": "DevOps", "location": "Remote", "level": "Intermediate", "description": "Manage CI/CD pipelines and Kubernetes clusters.", "required_skills": '["Linux", "Docker", "Kubernetes", "CI/CD"]', "apply_url": None},
    {"title": "iOS Developer Intern", "company": "AppWorks Studio", "domain": "Mobile Development", "location": "Mumbai, India", "level": "Beginner", "description": "Build iOS apps using Swift and Xcode.", "required_skills": '["Swift", "Xcode", "UIKit"]', "apply_url": None},
    {"title": "Android Developer Intern", "company": "MobileFirst", "domain": "Mobile Development", "location": "Remote", "level": "Intermediate", "description": "Build Android apps using Kotlin and Jetpack Compose.", "required_skills": '["Kotlin", "Android Studio", "Jetpack Compose"]', "apply_url": None},
    {"title": "Cybersecurity Analyst Intern", "company": "SecureOps", "domain": "Cybersecurity", "location": "Remote", "level": "Beginner", "description": "Assist in vulnerability assessments and security audits.", "required_skills": '["Networking", "Linux", "Python", "Security Tools"]', "apply_url": None},
    {"title": "Blockchain Developer Intern", "company": "ChainTech", "domain": "Blockchain", "location": "Remote", "level": "Intermediate", "description": "Build smart contracts and DApps on Ethereum.", "required_skills": '["Solidity", "Web3.js", "Ethereum", "JavaScript"]', "apply_url": None},
]


async def seed():
    await init_db()
    async with AsyncSessionLocal() as session:
        # Seed badges
        existing_badges = await session.execute(select(Badge))
        if not existing_badges.scalars().first():
            for b in BADGES:
                session.add(Badge(**b))
            print(f"✅ Seeded {len(BADGES)} badges")
        else:
            print("ℹ️  Badges already seeded")

        # Seed internships
        existing_internships = await session.execute(select(Internship))
        if not existing_internships.scalars().first():
            for i in INTERNSHIPS:
                session.add(Internship(**i))
            print(f"✅ Seeded {len(INTERNSHIPS)} internships")
        else:
            print("ℹ️  Internships already seeded")

        await session.commit()
    print("🚀 Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
