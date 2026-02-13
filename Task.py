import datetime
from typing import Optional
from datetime import date, datetime
from click import DateTime
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, Integer, Nullable, String, create_engine, Date, DateTime
from sqlalchemy.orm import (
    sessionmaker,
    declarative_base,
    Session,
    Mapped,
    mapped_column,
)
import enum

app = FastAPI()

DATABASE_URL = "sqlite:///./tasks.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Stutus(str, enum.Enum):
    PENDING = "pending"
    IN_PROCESS = "in-process"
    COMPLETED = "completed"


class TaskDB(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    priority: Mapped[Priority] = mapped_column(default=Priority.MEDIUM)
    status: Mapped[Stutus] = mapped_column(default=Stutus.PENDING)
    due_date = Column(Date, nullable=False)
    completed_at = Column(DateTime, nullable=True)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: Optional[Priority] = None
    status: Optional[Stutus] = None
    due_date: date
    completed_at: Optional[datetime] = None


class TaskResponse(BaseModel):
    id: int
    title: str
    priority: str
    status: str
    due_date: date
    completed_at: Optional[datetime] = None


class StatsResponse(BaseModel):
    total: int = 0
    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    overdue: int = 0
    high_priority_pending: int = 0


@app.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    if task.due_date <= date.today():
        raise HTTPException(
            status_code=422, detail="please enter the today or future date!!"
        )
    db_task = TaskDB(**task.model_dump())
    if task.priority == "high":
        db_high_task = (
            db.query(TaskDB)
            .filter(TaskDB.priority == "high" and TaskDB.status == "pending")
            .count()
        )
        print(db_high_task)
        if db_high_task >= 5:
            raise HTTPException(
                status_code=422,
                detail="in database have already more than 5 high task!!",
            )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


@app.get("/tasks", response_model=list[TaskResponse])
def get_task(
    page: int | None = None,
    limit: int | None = None,
    status: str | None = None,
    priority: str | None = None,
    overdue: bool = False,
    starttitle:str|None=None,
    search:str| None=None,
    endtitle:str|None=None,
    db: Session = Depends(get_db),
):
    db_task = db.query(TaskDB).all()
    db_status = []
    db_priority = []
    db_overdue = []
    db_pages = []
    if starttitle:
        db_title=db.query(TaskDB).filter(TaskDB.title.ilike(f"{starttitle}%"))
        return db_title
    if endtitle:
        db_title=db.query(TaskDB).filter(TaskDB.title.ilike(f"%{endtitle}"))
        return db_title
    if search:
        db_title_dec=db.query(TaskDB).filter((TaskDB.title.ilike(f"%{search}%")) | (TaskDB.description.ilike(f"%{search}%")))
        return db_title_dec
    if page is not None and limit is not None:
        for i in range((page - 1) * limit, ((page - 1) * limit) + limit):
            db_pages.append(db_task[i])
        return db_pages
    if overdue:
        for task in db_task:
            if date.today() > task.due_date and status != "completed":
                db_overdue.append(task)
        return db_overdue
    if status is not None:
        for task in db_task:
            if task.status == status:
                db_status.append(task)
        return db_status
    if priority is not None:
        for task in db_task:
            if task.priority == priority:
                db_priority.append(task)
        return db_priority
    # if title is not None:
    #     for task in db_task:
    #         if (task.title).startswith(title):
    #             db_title.append(task)
    #     return db_title
    return db_task


@app.get("/tasks/stats", response_model=StatsResponse)
def stats(db: Session = Depends(get_db)):
    stat = {
        "total": 0,
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "overdue": 0,
        "high_priority_pending": 0,
    }
    db_task = db.query(TaskDB).all()
    stat["total"] = len(db_task)
    for task in db_task:
        if task.status == "pending":
            stat["pending"] = stat["pending"] + 1
        if task.status == "in-process":
            stat["in-process"] = stat["in-process"] + 1
        if task.status == "completed":
            stat["completed"] = stat["completed"] + 1
        if task.due_date < date.today():
            stat["overdue"] = stat["overdue"] + 1
        if task.priority == "high" and task.status == "pending":
            stat["high_priority_pending"] = stat["high_priority_pending"] + 1
    db_stat = StatsResponse(**stat)
    return db_stat


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task_id(task_id: int, db: Session = Depends(get_db)):
    db_task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if db_task is None:
        raise HTTPException(status_code=422, detail="please enter valid id!!")
    return db_task


@app.put("/tasks/{task_id}", response_model=TaskResponse)
def update_by_id(task_id: int, task: TaskCreate, db: Session = Depends(get_db)):
    db_task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if db_task is None:
        raise HTTPException(status_code=422, detail="please enter valid id!!")
    if task.priority == "high":
        db_high_task = (
            db.query(TaskDB)
            .filter(TaskDB.priority == "high" and TaskDB.status == "pending")
            .count()
        )
        if db_high_task >= 5:
            raise HTTPException(
                status_code=422,
                detail="in database have already more than 5 high task!!",
            )
    if (
        (db_task.status == "pending" and task.status == "in-process")
        or (db_task.status == "in-process" and task.status == "completed")
        or (db_task.status == task.status)
    ):
        db_task.title = task.title
        db_task.description = task.description
        db_task.priority = task.priority
        db_task.status = task.status
        db_task.due_date = task.due_date
        if task.status == "completed":
            db_task.completed_at = datetime.now()
        else:
            db_task.completed_at = task.completed_at
        db.commit()
        db.refresh(db_task)
        return db_task
    else:
        raise HTTPException(status_code=422, detail="please enter valid status!!")


@app.delete("/tasks/{task_id}", response_model=TaskResponse)
def delete_by_id(task_id: int, db: Session = Depends(get_db)):
    db_task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if db_task is None:
        raise HTTPException(status_code=422, detail="please enter valid id!!")
    db.delete(db_task)
    db.commit()
    raise HTTPException(status_code=204, detail="deleted successfully!!")
