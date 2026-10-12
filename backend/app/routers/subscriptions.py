from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import AiService, Subscription
from app.schemas import SubscriptionIn, SubscriptionOut, SubscriptionUpdate

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


def _get_own(db: DbSession, user: CurrentUser, subscription_id: int) -> Subscription:
    sub = db.get(Subscription, subscription_id)
    if sub is None or sub.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "구독 정보를 찾을 수 없습니다")
    return sub


@router.get("", response_model=list[SubscriptionOut])
def list_subscriptions(db: DbSession, user: CurrentUser) -> list[Subscription]:
    return list(
        db.scalars(select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.id))
    )


@router.post("", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
def create_subscription(body: SubscriptionIn, db: DbSession, user: CurrentUser) -> Subscription:
    if db.get(AiService, body.service_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "존재하지 않는 서비스입니다")
    sub = Subscription(user_id=user.id, **body.model_dump())
    db.add(sub)
    db.commit()
    return sub


@router.patch("/{subscription_id}", response_model=SubscriptionOut)
def update_subscription(
    subscription_id: int, body: SubscriptionUpdate, db: DbSession, user: CurrentUser
) -> Subscription:
    sub = _get_own(db, user, subscription_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(sub, key, value)
    db.commit()
    return sub


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(subscription_id: int, db: DbSession, user: CurrentUser) -> None:
    db.delete(_get_own(db, user, subscription_id))
    db.commit()
