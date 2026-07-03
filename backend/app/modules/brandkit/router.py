import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import CurrentUser, get_current_user, get_tenant_db
from app.modules.brandkit.models import BrandAsset

router = APIRouter(prefix="/api/brandkit", tags=["brandkit"])

KINDS = {"company_intro", "product", "certification", "case", "faq"}


class AssetIn(BaseModel):
    kind: str
    title: str
    content: dict = {}
    ai_quotable: bool = True


class AssetOut(AssetIn):
    id: str


def _out(a: BrandAsset) -> AssetOut:
    return AssetOut(id=str(a.id), kind=a.kind, title=a.title,
                    content=a.content, ai_quotable=a.ai_quotable)


@router.get("", response_model=list[AssetOut])
def list_assets(current: CurrentUser = Depends(get_current_user),
                db: Session = Depends(get_tenant_db)) -> list[AssetOut]:
    rows = db.execute(select(BrandAsset).where(BrandAsset.tenant_id == current.tenant_id)
                      .order_by(BrandAsset.created_at)).scalars().all()
    return [_out(a) for a in rows]


@router.post("", response_model=AssetOut, status_code=201)
def create_asset(body: AssetIn, current: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_tenant_db)) -> AssetOut:
    if body.kind not in KINDS:
        raise HTTPException(422, f"kind 必须是 {sorted(KINDS)} 之一")
    asset = BrandAsset(tenant_id=current.tenant_id, **body.model_dump())
    db.add(asset)
    db.commit()
    return _out(asset)


@router.put("/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: uuid.UUID, body: AssetIn,
                 current: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_tenant_db)) -> AssetOut:
    asset = db.get(BrandAsset, asset_id)
    if asset is None or asset.tenant_id != current.tenant_id:
        raise HTTPException(404, "资产不存在")
    for k, v in body.model_dump().items():
        setattr(asset, k, v)
    db.commit()
    return _out(asset)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: uuid.UUID, current: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_tenant_db)) -> None:
    asset = db.get(BrandAsset, asset_id)
    if asset is None or asset.tenant_id != current.tenant_id:
        raise HTTPException(404, "资产不存在")
    db.delete(asset)
    db.commit()
