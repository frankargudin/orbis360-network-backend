"""Network link endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.domain.models.network import Link
from app.infrastructure.database.session import get_db
from app.schemas.network import LinkCreate, LinkOut

router = APIRouter(prefix="/links", tags=["links"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[LinkOut])
async def list_links(
    status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    query = select(Link)
    if status:
        query = query.where(Link.status == status)
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=LinkOut, status_code=201)
async def create_link(body: LinkCreate, db: AsyncSession = Depends(get_db)):
    link = Link(**body.model_dump())
    db.add(link)
    await db.flush()
    await db.refresh(link)
    return link


@router.delete("/{link_id}", status_code=204)
async def delete_link(link_id: UUID, db: AsyncSession = Depends(get_db)):
    link = await db.get(Link, link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
