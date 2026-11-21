import sys

sys.path.insert(0, '/tmp/T-159-steelworks/backend')

from app.core.database import SessionLocal
from tests.helpers import (
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
    make_tenant,
    make_user,
)
from app.services.inventory import link_coil

db = SessionLocal()
tenant = make_tenant(db, name='T-159 Manual')
user = make_user(db, tenant, email='operario@manual.local', role='operator')
material = make_material(db, tenant, code='ACERO-MANUAL', cost=2.0, density=7850)
bobina = make_stock_item(
    db, tenant, material, cantidad=1000.0, lote='L-MANUAL',
    ancho=122.0, espesor=0.5, ubicacion='LINEA-1',
)
orden = make_order(db, tenant, numero='OP-MANUAL')
linea = make_order_line(db, orden, workstation='LINEA-1', total_quantity=50.0)
linea.meters_per_piece = 2.0
db.commit()
link_coil(db, tenant.id, user.id, stock_item_id=bobina.id, order_id=orden.id, line_id=linea.id)
db.commit()
print(
    'TENANT', tenant.id,
    'USER', user.id,
    'ORDER', orden.id,
    'LINE', linea.id,
    'COIL', bobina.id,
)
db.close()
