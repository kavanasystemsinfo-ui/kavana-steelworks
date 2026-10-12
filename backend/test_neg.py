#!/usr/bin/env python3
"""Test negative quantity in consume_stock_fifo to see if stock increases."""
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import app models and services
sys.path.insert(0, '.')
from app.models import Tenant, User, Material, StockItem, Order, OrderLine
from app.services.inventory import consume_stock_fifo
from tests.helpers import make_tenant, make_user, make_material, make_stock_item, make_order, make_order_line

def main():
    # Create in-memory SQLite database
    engine = create_engine("sqlite:///:memory:", echo=False)
    # Create tables
    from app.models import Base
    Base.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # Create tenant, user
        tenant = make_tenant(db, name="TestTenant", slug="test")
        user = make_user(db, tenant, email="operario@test.local", role="operator")
        
        # Create material
        material = make_material(db, tenant, cost=2.0)
        # Set initial stock_current for material
        material.stock_current = 100.0
        db.add(material)
        db.commit()
        
        # Create stock item with some quantity
        stock_item = make_stock_item(
            db,
            tenant,
            material,
            cantidad=50.0,
            lote="NEGTEST",
            coste=2.0,
        )
        db.add(stock_item)
        db.commit()
        
        # Create order and line
        order = make_order(db, tenant, numero="NEG-OP")
        line = make_order_line(db, order, workstation="LINEA-1")
        db.add(order)
        db.add(line)
        db.commit()
        
        print(f"Before: material.stock_current = {material.stock_current}")
        print(f"StockItem cantidad_disponible = {stock_item.cantidad_disponible}")
        
        # Call consume_stock_fifo with negative quantity
        from decimal import Decimal
        neg_qty = Decimal("-10.0")  # try to remove -10 kg (i.e., add 10 kg)
        result = consume_stock_fifo(
            db,
            tenant.id,
            user.id,
            material_id=material.id,
            cantidad_requerida=neg_qty,
            order_id=order.id,
            order_line_id=line.id,
        )
        
        db.commit()
        db.refresh(material)
        db.refresh(stock_item)
        
        print(f"After: material.stock_current = {material.stock_current}")
        print(f"StockItem cantidad_disponible = {stock_item.cantidad_disponible}")
        print(f"Result: {result}")
        
        # Check if stock increased (i.e., stock_current > initial 100)
        if material.stock_current > 100.0:
            print("SUCCESS: Stock increased due to negative quantity!")
            return 0
        else:
            print("FAIL: Stock did not increase.")
            return 1
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()

if __name__ == "__main__":
    sys.exit(main())