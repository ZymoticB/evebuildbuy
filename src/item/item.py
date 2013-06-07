import sys
import requests

import xml.etree.ElementTree as ET
from collections import defaultdict, Counter

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
    SELECT t.typeID, g.categoryID, g.groupID
    FROM invTypes as t
      INNER JOIN invGroups as g
        ON (t.groupID = g.groupID)
    WHERE typeName=%s
    """
EVE_CENTRAL_QUERY="http://api.eve-central.com/api/marketstat?typeid={item}&regionlimit={region}"
JITA_REGION_ID='10000002'
ITEM_CACHE={}

class UnknownItemException(Exception):
    pass

def ItemFactory(db, name, me=0, pe=5, cache=True, part_me=0):
    if name in ITEM_CACHE and cache:
        item = ITEM_CACHE[name]
        if item.me == me and item.part_me == part_me:
            return ITEM_CACHE[name]
        else:
            #recreate
            pass
    item = ManufacturableItem(db, name, me=me, pe=pe, part_me=part_me)
    ITEM_CACHE[name] = item
    return item


class ManufacturableItem(object):

    def __init__(self, db, name, source="sell", me=0, pe=5, part_me=0):
        print "start: " + name
        if "_" in name:
            self.name = name.replace('_', ' ')
        else:
            self.name = name
        self.db = db
        self.source = source
        self.me = me
        self.pe = pe
        self.part_me = part_me
        self.is_jf = self.name in ['ark', 'rhea', 'ahshar', 'nomad']
        _info_query = self.db.get(ITEM_INFO_QUERY, self.name)
        if _info_query is None:
            raise UnknownItemException(self.name)
        self.id = _info_query.typeID
        self.groupID = _info_query.groupID
        self.categoryID = _info_query.categoryID
        _blueprint_query = self.db.get("SELECT blueprintTypeID,wasteFactor FROM invBlueprintTypes WHERE productTypeID=%s", self.id)
        if _blueprint_query is None:
            #probably a base material, that is cool
            #also could be a skill
            #get price off of eve central
            #TODO validate based on category that it is base mat
            #Nothing else to do!
            return
        self.blueprintID = _blueprint_query.blueprintTypeID
        self.waste_factor = _blueprint_query.wasteFactor
        print "end: " + name

    def to_dict(self):
        minsell = self.minsell
        maxbuy = self.maxbuy
        cost = self.cost
        profit = self.profit
        minerals = self.minerals
        parts = []
        for part in self.parts:
            parts.append({
                "name": part['name'],
                "quantity": part['quantity'],
                "part": part['part'].to_dict(),
            })
        return {
            "minsell": minsell,
            "maxbuy": maxbuy,
            "cost": cost,
            "profit": profit,
            "parts": parts,
            "minerals": minerals,
            "name": self.name
        }

    @property
    def base_parts(self):
        if not hasattr(self, '_base_parts'):
            parts = self.db.query(REPROCESS_QUERY, self.id)
            self._base_parts = [(ItemFactory(self.db, p.typeName, me=self.part_me), p.quantity) for p in parts]
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
    def minerals(self):
        if not hasattr(self, '_minerals'):
            if self.categoryID == 4:
                self._minerals = Counter()
            else:
                minerals = Counter()
                for part in self.parts:
                    if part['part'].categoryID == 4:
                        minerals.update({part['name']: part['quantity']})
                    else:
                        quantity = part['quantity']
                        for i in range(quantity):
                            minerals.update(part['part'].minerals)
                self._minerals = minerals
        return self._minerals


    @property
    def extra_materials(self):
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
                    extra_mats["skills"].append((ItemFactory(self.db, mat.typeName, me=self.part_me), mat.quantity))
                elif mat.recycle:
                    #this is a T1 required by a T2. We need to delete the reprocess cost from mat cost
                    extra_mats["recycle"].append((ItemFactory(self.db, mat.typeName, me=self.part_me), mat.quantity))
                else:
                    #Just a normal extra mat
                    if mat.categoryID == 17:
                        #This is a "commodity" so something we can calc profit on aka part
                        extra_mats["parts"].append((ItemFactory(self.db, mat.typeName, me=self.part_me), mat.quantity, mat.damagePerJob))
                    elif mat.categoryID == 4:
                        #This is a mineral
                        extra_mats["minerals"].append((ItemFactory(self.db, mat.typeName, me=self.part_me), mat.quantity, mat.damagePerJob))
            self._extra_materials = extra_mats
        return self._extra_materials

    @property
    def prices(self):
        if not hasattr(self, "_prices"):
            shitxml = requests.get(EVE_CENTRAL_QUERY.format(item=self.id, region=JITA_REGION_ID))
            rootshit = ET.fromstring(shitxml.text)
            item = rootshit[0][0]
            prices = {"maxbuy": float(item.find('buy').find('max').text),
                    "minsell": float(item.find('sell').find('min').text),
            }
            self._prices = prices
        return self._prices

    @property
    def maxbuy(self):
        return self.prices['maxbuy']

    @property
    def minsell(self):
        return self.prices['minsell']

    @property
    def parts(self):
        if not hasattr(self, '_parts'):
            if self.categoryID == 4:
                #This is a mineral
                self._parts = []
            else:
                parts = []
                minerals_to_remove = defaultdict(int)
                for item,quantity in self.extra_materials['recycle']:
                    #Assume pe5 for extra material waste
                    for part in item.parts:
                        if self.is_jf:
                            parts.append(part)
                        minerals_to_remove[part['name']] += part['quantity']

                for part,quantity in self.base_parts:
                    quantity = self.after_waste(quantity)
                    if part.name in minerals_to_remove:
                        new_total = quantity - minerals_to_remove[part.name]
                        if new_total > 0:
                            parts.append({
                                "name": part.name,
                                "quantity": new_total,
                                "part": ItemFactory(self.db, part.name, me=self.part_me)
                            })
                    else:
                        parts.append({
                            "name": part.name,
                            "quantity": quantity,
                            "part": ItemFactory(self.db, part.name, me=self.part_me)
                        })

                for part,quantity,damage in self.extra_materials['parts']:
                    #ignore damage. small opimization that only leads to extra profit
                    #as long as the items are repaired instead of rebuild
                    parts.append({
                        "name": part.name,
                        "quantity": quantity,
                        "part": ItemFactory(self.db, part.name, me=self.part_me)
                    })

                for part,quantity,__damage in self.extra_materials['minerals']:
                    #ignore damage these are minerals
                    parts.append({
                        "name": part.name,
                        "quantity": quantity,
                        "part": ItemFactory(self.db, part.name, me=self.part_me)
                    })

                self._parts = parts
        return self._parts

    @property
    def cost(self):
        if not hasattr(self, '_cost'):
            if self.categoryID == 4:
                #this is a mineral
                self._cost = self.minsell
            else:
                total = 0
                if self.source=='sell':
                    for part in self.parts:
                        item_name = part['name']
                        quantity = part['quantity']
                        item = ItemFactory(self.db, item_name, me=self.part_me)
                        total += item.minsell * (quantity)
                if self.source=='buy':
                    for part in self.parts:
                        item_name = part['name']
                        quantity = part['quantity']
                        item = ItemFactory(self.db, item_name, me=self.part_me)
                        total += item.minsell * (quantity)
                self._cost = total
        return self._cost

    @property
    def profit(self):
        return self.minsell - self.cost

def main():
    db = Connection('localhost', 'evedump', user='eve', password='4Td#xA3c.0)J;Ni_k$(E')

    item = ItemFactory(db,sys.argv[1])
    print item.cost
    print item.minsell
    print item.profit



if __name__ == "__main__":
    main()
