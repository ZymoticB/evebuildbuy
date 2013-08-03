import sys
import requests

from collections import defaultdict, Counter
import constants

from .evecentral import get_price

REPROCESS_QUERY = """
    SELECT t2.typeName,t2.typeID,t1.quantity
    FROM invTypeMaterials as t1
        INNER JOIN invTypes as t2
        ON(t1.materialTypeID=t2.typeID)
    WHERE t1.typeID=%s"""

EXTRA_MAT_QUERY = """
    SELECT t.typeName, t.typeID, r.quantity, r.damagePerJob, r.recycle, g.categoryID
    FROM ramTypeRequirements as r
      INNER JOIN invTypes as t
        ON (r.requiredTypeID = t.typeID)
      INNER JOIN invGroups as g
        ON (t.groupID = g.groupID)
    WHERE r.typeID=%s AND r.activityID='1'
    """
ITEM_INFO_QUERY = """
    SELECT t.typeID, t.volume, g.categoryID, g.groupID, g.groupName
    FROM invTypes as t
      INNER JOIN invGroups as g
        ON (t.groupID = g.groupID)
    WHERE typeName=%s
    """

ITEM_TYPE_QUERY = """
    SELECT b.techLevel, g.categoryID
    FROM invTypes as t
      INNER JOIN invBlueprintTypes as b
        ON (t.typeID = b.productTypeID)
      INNER JOIN invGroups as g
        ON (t.groupID = g.groupID)
    WHERE t.typeName=%s
    """
class UnknownItemException(Exception):
    pass

def ItemFactory(db, name, me=0, pe=5):
    name = name.replace('_', ' ')
    _item_type_query = db.get(ITEM_TYPE_QUERY, name)
    if _item_type_query is None:
        raise UnknownItemException(self.name)
    else:
        tech = _item_type_query.techLevel
        category = _item_type_query.categoryID
    is_jf = name in ['ark', 'rhea', 'anshar', 'nomad']
    if is_jf:
        return JFItem(db, name, "sell", me, pe)
    elif category == 4 or category == 43:
        return BaseMaterial(db, name, "sell", me, pe)
    elif tech == 1:
        return T1Item(db, name, "sell", me, pe)
    elif tech == 2:
        return T2Item(db, name, "sell", me, pe)
    elif tech == 3:
        return T3Item(db, name, "sell", me, pe)

class ManufacturableItem(object):
    """
    Base manufacturable EVE item

    This should be subclasses for a specific type as the EVE
    db is super akward to work with in a general way w.r.t.
    T1/T2/T3/Capitals/JFs
    """
    def __init__(self, db, name, price_source="sell", me=0, pe=5):
        self.name = name
        self.db = db
        self.price_source = price_source
        self.me = me
        self.pe = pe
        _info_query = self.db.get(ITEM_INFO_QUERY, self.name)
        self._id = _info_query.typeID
        self.groupID = _info_query.groupID
        self.categoryID = _info_query.categoryID
        self.groupName = _info_query.groupName
        try:
            self.packaged_size = constants.PACKAGED_SIZE[self.groupName]
        except KeyError:
            self.packaged_size = _info_query.volume
        _blueprint_query = self.db.get("SELECT blueprintTypeID,wasteFactor FROM invBlueprintTypes WHERE productTypeID=%s", self._id)
        if _blueprint_query is None:
            #probably a base material, that is cool
            #also could be a skill
            #get price off of eve central
            #TODO validate based on category that it is base mat
            #Nothing else to do!
            self.is_manufacturable = False
            return
        self.is_manufacturable = True
        self.blueprintID = _blueprint_query.blueprintTypeID
        self.waste_factor = _blueprint_query.wasteFactor

    def _get_id(self, item_name):
        _id_query = self.db.get("SELECT typeID FROM invTypes WHERE typeName=%s", item_name)
        if _id_query is None:
            raise UnknownItemException()
        else:
            return _id_query.typeID

    def to_dict(self):
        minsell = self.minsell
        maxbuy = self.maxbuy
        cost = self.cost
        profit = self.profit
        parts = []
        for part in self.parts:
            parts.append({
                "name": part['name'],
                "quantity": part['quantity'],
            })
        return {
            "minsell": minsell,
            "maxbuy": maxbuy,
            "cost": cost,
            "profit": profit,
            "parts": parts,
            "packaged_size": self.packaged_size,
            "name": self.name,
            "skills": self.extra_materials["skills"],
        }

    @property
    def base_parts(self):
        if not self.is_manufacturable:
            return []
        if not hasattr(self, '_base_parts'):
            parts = self.db.query(REPROCESS_QUERY, self._id)
            self._base_parts = [(p.typeName, p.quantity) for p in parts]
        return self._base_parts

    def after_waste(self, base):
        pe_waste_factor = (25 - (5*self.pe))/100.0
        if self.me>=0:
            me_waste_factor = self.waste_factor/100.0*(1/float(self.me+1))
        else:
            me_waste_factor = self.waste_factor/100.0*float(1-self.me)
        total_waste = round(pe_waste_factor * base) + round(me_waste_factor * base)
        print "base: %s waste %s" %(base, total_waste)
        return int(round(base + total_waste))

    @property
    def extra_materials(self):
        if not self.is_manufacturable:
            return []
        if not hasattr(self, '_extra_materials'):
            extra_mats = {"skills": [],
                "minerals": [],
                "parts": [],
                "recycle": [],
            }
            _all = self.db.query(EXTRA_MAT_QUERY, self.blueprintID)
            for mat in _all:
                if mat.categoryID == 16:
                    #this is a skill
                    extra_mats["skills"].append((mat.typeName, mat.quantity))
                elif mat.recycle:
                    #this is a T1 required by a T2. We need to delete the reprocess cost from mat cost
                    extra_mats["recycle"].append((mat.typeName, mat.quantity))
                else:
                    #Just a normal extra mat
                    extra_mats["parts"].append(((mat.typeName, mat.quantity, mat.damagePerJob)))
            self._extra_materials = extra_mats
        return self._extra_materials

    @property
    def prices(self):
        if not hasattr(self, "_prices"):
            self._prices = get_price(self._id)
        return self._prices

    @property
    def maxbuy(self):
        return self.prices['maxbuy']

    @property
    def minsell(self):
        return self.prices['minsell']

    @property
    def cost(self):
        if not hasattr(self, '_cost'):
            if self.categoryID == 4:
                #this is a mineral
                self._cost = self.minsell
            else:
                total = 0
                if self.price_source=='sell':
                    for part in self.parts:
                        item_name = part['name']
                        quantity = part['quantity']
                        item_cost = part['price']['minsell']
                        total += item_cost * (quantity)
                if self.price_source=='buy':
                    for part in self.parts:
                        item_name = part['name']
                        quantity = part['quantity']
                        item_cost = part['price']['maxbuy']
                        total += item_cost * (quantity)
                self._cost = total
        return self._cost

    @property
    def parts(self):
        if not hasattr(self, '_parts'):
            self._parts = self.get_parts()
        return self._parts

    def get_parts(self):
        raise NotImplementedError
    @property
    def profit(self):
        return self.minsell - self.cost

class BaseMaterial(ManufacturableItem):
    """
    Minerals and PI mats have no parts
    """
    def get_parts(self):
        return []

class JFItem(ManufacturableItem):
    """
    Jump Freighters

    they are awkwardly subtley different than other T2 items
    """
    def get_parts(self):
        parts = []
        for item,quantity in self.extra_materials['recycle']:
            #Assume pe5 for extra material waste
            for part in item.parts:
                parts.append({
                    "name": part,
                    "quantity": quantity,
                    "price": get_price(self._get_id(item))
                })

        for part,quantity in self.base_parts:
            quantity = self.after_waste(quantity)
            if part in minerals_to_remove:
                new_total = quantity - minerals_to_remove[part]
                if new_total > 0:
                    parts.append({
                        "name": part,
                        "quantity": quantity,
                        "price": get_price(self._get_id(part))
                    })
            else:
                parts.append({
                    "name": part,
                    "quantity": quantity,
                    "price": get_price(self._get_id(part))
                })
        for part,quantity,damage in self.extra_materials['parts']:
            #ignore damage. small opimization that only leads to extra profit
            #as long as the items are repaired instead of rebuild
            parts.append({
                "name": part,
                "quantity": quantity,
                "price": get_price(self._get_id(part))
            })
        for item,quantity in self.extra_materials['recycle']:
            #Assume pe5 for extra material waste
            for part in item.parts:
                minerals_to_remove[part['name']] += part['quantity']

class T1Item(ManufacturableItem):
    """
    T1 Manufacturable Item
    """
    def get_parts(self):
        parts = []
        for part,quantity in self.base_parts:
            quantity = self.after_waste(quantity)
            parts.append({
                "name": part,
                "quantity": quantity,
                "price": get_price(self._get_id(part))
            })
        for part,quantity,damage in self.extra_materials['parts']:
            #ignore damage. small opimization that only leads to extra profit
            #as long as the items are repaired instead of rebuild
            parts.append({
                "name": part,
                "quantity": quantity,
                "price": get_price(self._get_id(part))
            })
        return parts

class T2Item(ManufacturableItem):
    """
    T2 Manufacturable Item
    """
    def get_parts(self):
        parts = []
        minerals_to_remove = defaultdict(int)
        for item,quantity in self.extra_materials['recycle']:
            #Assume pe5 for extra material waste
            for part in item.parts:
                minerals_to_remove[part['name']] += part['quantity']

        for part,quantity in self.base_parts:
            quantity = self.after_waste(quantity)
            if part in minerals_to_remove:
                new_total = quantity - minerals_to_remove[part]
                if new_total > 0:
                    parts.append({
                        "name": part,
                        "quantity": quantity,
                        "price": get_price(self._get_id(part))
                    })
            else:
                parts.append({
                    "name": part,
                    "quantity": quantity,
                    "price": get_price(self._get_id(part))
                })
        for part,quantity,damage in self.extra_materials['parts']:
            #ignore damage. small opimization that only leads to extra profit
            #as long as the items are repaired instead of rebuild
            parts.append({
                "name": part,
                "quantity": quantity,
                "price": get_price(self._get_id(part))
            })

class T3Item(ManufacturableItem):
    """
    T2 Manufacturable Item
    """
    def get_parts(self):
        parts = []
        minerals_to_remove = defaultdict(int)
        for item,quantity in self.extra_materials['recycle']:
            #Assume pe5 for extra material waste
            for part in item.parts:
                minerals_to_remove[part['name']] += part['quantity']

        for part,quantity in self.base_parts:
            quantity = self.after_waste(quantity)
            if part in minerals_to_remove:
                new_total = quantity - minerals_to_remove[part]
                if new_total > 0:
                    parts.append({
                        "name": part,
                        "quantity": quantity,
                        "price": get_price(self._get_id(part))
                    })
            else:
                parts.append({
                    "name": part,
                    "quantity": quantity,
                    "price": get_price(self._get_id(part))
                })
        for part,quantity,damage in self.extra_materials['parts']:
            #ignore damage. small opimization that only leads to extra profit
            #as long as the items are repaired instead of rebuild
            parts.append({
                "name": part,
                "quantity": quantity,
                "price": get_price(self._get_id(part))
            })

def main():
    from torndb import Connection
    db = Connection('localhost', 'evedump', user='eve', password='eeph5aimohtheejieg1B')

    item = ItemFactory(db,sys.argv[1])
    print item.cost
    print item.minsell
    print item.profit



if __name__ == "__main__":
    main()
