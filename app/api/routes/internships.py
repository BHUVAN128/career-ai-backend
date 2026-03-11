from urllib.parse import quote_plus
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User, UserProfile
from app.models.roadmap import Roadmap
from app.schemas.internships import InternshipsResponse, InternshipRecommendation
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/internships", tags=["internships"])


def _domain_skills(domain: str) -> list:
    mapping = {
        "web": ["HTML/CSS", "JavaScript", "React", "Node.js", "Git"],
        "frontend": ["HTML/CSS", "JavaScript", "React", "TypeScript", "Git"],
        "backend": ["Python/Node.js", "REST APIs", "Databases", "Docker", "Git"],
        "full stack": ["React", "Node.js", "Databases", "REST APIs", "Git"],
        "data science": ["Python", "Pandas", "Machine Learning", "SQL", "Statistics"],
        "machine learning": ["Python", "TensorFlow/PyTorch", "Scikit-learn", "MLOps", "Statistics"],
        "artificial intelligence": ["Python", "Deep Learning", "NLP", "Computer Vision", "MLOps"],
        "android": ["Kotlin", "Java", "Android SDK", "Jetpack Compose", "Git"],
        "ios": ["Swift", "SwiftUI", "UIKit", "Xcode", "Git"],
        "mobile": ["React Native / Flutter", "iOS/Android SDK", "REST APIs", "Git", "UI/UX"],
        "devops": ["Docker", "Kubernetes", "CI/CD", "Linux", "Cloud (AWS/GCP)"],
        "cloud": ["AWS/GCP/Azure", "Docker", "Terraform", "Linux", "Networking"],
        "cybersecurity": ["Networking", "Linux", "Python", "Penetration Testing", "SIEM"],
        "ui/ux": ["Figma", "User Research", "Prototyping", "CSS", "Design Systems"],
        "blockchain": ["Solidity", "Web3.js", "Smart Contracts", "Ethereum", "DeFi"],
        "game": ["Unity/Unreal", "C#/C++", "3D Modelling", "Physics", "Git"],
        "embedded": ["C/C++", "RTOS", "Microcontrollers", "Linux", "Electronics"],
    }
    domain_lower = domain.lower()
    for key, skills in mapping.items():
        if key in domain_lower:
            return skills
    return ["Programming", "Problem Solving", "Communication", "Git", "Agile"]


def _build_platform_data(domain: str) -> dict:
    """
    Build guaranteed-valid, properly URL-encoded search URLs for each platform.
    URLs are constructed entirely in Python - the LLM is NOT involved in URL generation.
    """
    q = quote_plus(f"{domain} internship")
    q_intern = quote_plus(f"{domain} intern")
    slug = domain.lower().replace(" ", "-").replace("/", "-").replace(".", "").strip("-")
    skills = _domain_skills(domain)

    return {
        "LinkedIn": {
            "url": f"https://www.linkedin.com/jobs/search/?keywords={q_intern}&f_JT=I",
            "description": f"World's largest professional network with thousands of {domain} intern roles updated daily. Filter by location, company size and work mode.",
            "skills": skills,
            "duration": "2-6 months",
            "location": "Remote / Hybrid / On-site",
            "stipend": None,
        },
        "Indeed": {
            "url": f"https://www.indeed.com/jobs?q={q}&fromage=14",
            "description": f"Aggregates {domain} internship listings from hundreds of company career pages and job boards, refreshed daily.",
            "skills": skills,
            "duration": "3-6 months",
            "location": "Remote / On-site (US & India)",
            "stipend": None,
        },
        "Internshala": {
            "url": f"https://internshala.com/internships/{slug}-internship/",
            "description": f"India's #1 internship platform with a dedicated {domain} category - thousands of verified listings from startups to large companies.",
            "skills": skills,
            "duration": "1-6 months",
            "location": "Remote / On-site (India)",
            "stipend": "Rs.5,000-40,000/month",
        },
        "Unstop": {
            "url": f"https://unstop.com/internships?oppType=internship&searchTerm={quote_plus(domain)}",
            "description": f"Competitions, hackathons and {domain} internships ideal for students wanting to build a portfolio while earning a stipend.",
            "skills": skills,
            "duration": "2-4 months",
            "location": "Remote / Hybrid (India)",
            "stipend": "Rs.5,000-25,000/month",
        },
        "Wellfound": {
            "url": f"https://wellfound.com/jobs?role=intern&q={quote_plus(domain)}",
            "description": f"Startup-focused board listing {domain} intern roles at VC-backed companies with full equity and stipend transparency.",
            "skills": skills,
            "duration": "3-6 months",
            "location": "Remote / Hybrid (Global)",
            "stipend": None,
        },
        "Naukri": {
            "url": f"https://www.naukri.com/{slug}-internship-jobs",
            "description": f"India's leading job portal with {domain} internship listings from MNCs, product companies and well-funded startups.",
            "skills": skills,
            "duration": "3-6 months",
            "location": "On-site / Hybrid (India)",
            "stipend": "Rs.10,000-40,000/month",
        },
        "Glassdoor": {
            "url": f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={q_intern}&jobType=internship",
            "description": f"Browse {domain} internships with salary transparency - see stipend ranges and company reviews before applying.",
            "skills": skills,
            "duration": "2-6 months",
            "location": "Remote / On-site (Global)",
            "stipend": None,
        },
        "SimplyHired": {
            "url": f"https://www.simplyhired.com/search?q={q}&jt=internship",
            "description": f"Aggregated {domain} internship listings with salary estimates, company ratings and one-click apply on many postings.",
            "skills": skills,
            "duration": "3-6 months",
            "location": "Remote / On-site (US)",
            "stipend": None,
        },
    }


@router.get("/recommendations", response_model=ApiResponse[InternshipsResponse])
async def get_internship_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return internship platform recommendations for the user's domain. Always accessible."""

    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    domain = (profile.domain or "Software Engineering") if profile else "Software Engineering"
    level = (profile.level or "Beginner") if profile else "Beginner"

    roadmap_result = await db.execute(
        select(Roadmap).where(
            Roadmap.user_id == current_user.id,
            Roadmap.is_active == True,
        )
    )
    roadmap = roadmap_result.scalar_one_or_none()
    total = roadmap.total_steps if roadmap else 0
    completed = roadmap.completed_steps if roadmap else 0
    completion_pct = round((completed / total * 100) if total > 0 else 0.0, 1)

    platform_data = _build_platform_data(domain)
    recommendations = [
        InternshipRecommendation(
            platform=platform,
            title=f"{domain} Internship on {platform}",
            description=data["description"],
            apply_url=data["url"],
            skills_needed=data["skills"],
            duration=data["duration"],
            stipend_range=data["stipend"],
            location=data["location"],
        )
        for platform, data in platform_data.items()
    ]

    return ApiResponse.ok(InternshipsResponse(
        eligible=True,
        domain=domain,
        level=level,
        completion_percent=completion_pct,
        recommendations=recommendations,
    ))
