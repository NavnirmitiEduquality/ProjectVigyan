from app.database import SessionLocal
from app.models import TLM


TLM_DATA = [
    {
        "name": "Electric Bell",
        "description": "Demonstrates the function and application of an electromagnet.",
    },
    {
        "name": "Newton's Disc",
        "description": "Demonstrates that white light is made up of seven colours.",
    },
    {
        "name": "Color Shadow",
        "description": "Demonstrates combinations of basic coloured lights and the formation of coloured shadows.",
    },
    {
        "name": "Periscope",
        "description": "Demonstrates the application of the laws of reflection.",
    },
    {
        "name": "Kaleidoscope",
        "description": "Demonstrates multiple reflection and formation of symmetrical images.",
    },
    {
        "name": "Laws Of Reflection",
        "description": "Demonstrates reflection from a plane mirror and the relationship between angle of incidence and angle of reflection.",
    },
    {
        "name": "Corner Mirror",
        "description": "Demonstrates multiple reflection and image formation using mirrors.",
    },
    {
        "name": "Infinity Tunnel",
        "description": "Demonstrates multiple reflections and repeated images between parallel and facing mirrors.",
    },
    {
        "name": "Magic water tap",
        "description": "Demonstrates an optical illusion involving a seemingly floating or continuously flowing water stream.",
    },
    {
        "name": "Total internal reflection",
        "description": "Demonstrates total internal reflection, bending of light rays and the principle used in optical fibre.",
    },
    {
        "name": "Simple camera",
        "description": "Demonstrates propagation of light and the basic principle of focusing using a lens.",
    },
    {
        "name": "Laws of inertia",
        "description": "Demonstrates Newton's first law and the tendency of an object to oppose a change in its state of rest.",
    },
    {
        "name": "Circle and ball",
        "description": "Demonstrates Newton's first law and the tendency of an object to oppose a change in its state of motion.",
    },
    {
        "name": "Action and reaction",
        "description": "Demonstrates Newton's third law of motion, where every action has an equal and opposite reaction.",
    },
    {
        "name": "Parrot in the cage",
        "description": "Demonstrates persistence of vision and how the eye can perceive two images together.",
    },
    {
        "name": "Zeotrope",
        "description": "Demonstrates persistence of vision and the basic concept behind motion pictures.",
    },
    {
        "name": "Pin screen",
        "description": "Demonstrates the relationship between pressure and area using a pin-based representation.",
    },
    {
        "name": "Floating ball",
        "description": "Demonstrates Bernoulli's principle and the effect of airflow on an object.",
    },
    {
        "name": "Floating fan",
        "description": "Demonstrates Bernoulli's principle, the relationship between airflow and speed, and aspects of action-reaction forces.",
    },
    {
        "name": "Tornado",
        "description": "Demonstrates atmospheric disturbances, air currents and storm formation.",
    },
    {
        "name": "Hand pump",
        "description": "Demonstrates application of pressure in pumping water and the pressure-volume relationship.",
    },
    {
        "name": "Floating magnets",
        "description": "Demonstrates properties of magnets, including attraction and repulsion.",
    },
    {
        "name": "Magnetic field tube",
        "description": "Demonstrates magnetic fields and properties of magnets.",
    },
    {
        "name": "Simple motor",
        "description": "Demonstrates electromagnetism and conversion of electromagnetic energy into mechanical energy.",
    },
    {
        "name": "Lazy tube",
        "description": "Demonstrates magnetic effects and eddy current behaviour.",
    },
    {
        "name": "Tower of Pisa",
        "description": "Demonstrates centre of gravity, gravitation and stability of structures.",
    },
    {
        "name": "Solar Light",
        "description": "Demonstrates conversion of solar light into electricity and the use of renewable solar energy.",
    },
    {
        "name": "Elliptical Carom Board",
        "description": "Demonstrates conic sections and properties of an ellipse.",
    },
    {
        "name": "Parking Puzzle",
        "description": "Demonstrates conic sections and properties of an ellipse.",
    },
    {
        "name": "Organ Pipes",
        "description": "Demonstrates sound at different frequencies and wavelengths using musical pipe arrangements.",
    },
    {
        "name": "Transverse wave pendulum",
        "description": "Demonstrates mechanical waves and the concept of transverse wave propagation.",
    },
    {
        "name": "Simple pendulum",
        "description": "Demonstrates the properties of a simple pendulum and the relationship between length and time period of oscillation.",
    },
    {
        "name": "Coupled pendulum",
        "description": "Demonstrates sympathetic swings and how connected pendulums can oscillate in harmony.",
    },
    {
        "name": "Cone run uphill",
        "description": "Demonstrates mass, centre of gravity and stability of structures.",
    },
    {
        "name": "Loop the loop",
        "description": "Demonstrates conversion of potential energy into kinetic energy and the effect of centrifugal force.",
    },
    {
        "name": "Ke Pe track",
        "description": "Demonstrates conversion between potential energy and kinetic energy.",
    },
    {
        "name": "Gyroscope",
        "description": "Demonstrates angular momentum and conservation of angular momentum.",
    },
    {
        "name": "Newton's cradle",
        "description": "Demonstrates conservation of momentum, conservation of energy and properties of collisions.",
    },
    {
        "name": "Lever",
        "description": "Demonstrates the principle of a lever and different types of levers.",
    },
    {
        "name": "Pulley block",
        "description": "Demonstrates the principle of a pulley as a simple machine.",
    },
    {
        "name": "Wheel and axle",
        "description": "Demonstrates how applying force farther from the centre makes rotation easier.",
    },
    {
        "name": "Fun with Magnets",
        "description": "Demonstrates types of magnets and their uses.",
    },
    {
        "name": "Viscosity tube",
        "description": "Demonstrates buoyancy or viscosity-related behaviour of materials in a tube.",
    },
    {
        "name": "wind mill",
        "description": "Demonstrates the principle of a windmill and conversion of wind energy into electrical energy.",
    },
    {
        "name": "Centrifuge puzzle",
        "description": "Demonstrates centrifugal force and how a centrifuge works.",
    },
    {
        "name": "conductors and Insulators",
        "description": "Demonstrates the difference between electrical conductors and insulators.",
    },
    {
        "name": "series and parallel circuits",
        "description": "Demonstrates the difference between series and parallel electrical circuits.",
    },
    {
        "name": "self balancing doll",
        "description": "Demonstrates mass, centre of gravity, gravitation and stability of structures.",
    },
    {
        "name": "electric maze",
        "description": "Provides an activity for concentration and demonstrates an electrical circuit through a maze.",
    },
    {
        "name": "shape of earth due to rotation",
        "description": "Demonstrates the effect of Earth's rotation on its shape.",
    },
    {
        "name": "heat absorption",
        "description": "Demonstrates the absorption of heat by different surfaces or materials.",
    },
    {
        "name": "funny mirrors",
        "description": "Demonstrates image distortion and different image effects produced by curved or specially shaped mirrors.",
    },
    {
        "name": "reflection and transmission",
        "description": "Demonstrates reflection and transmission of light.",
    },
    {
        "name": "Hand batteries",
        "description": "Demonstrates electric potential difference, electric batteries and the chemical effect of electric current.",
    },
    {
        "name": "Lateral shift",
        "description": "Demonstrates the lateral displacement of a light ray passing through a transparent medium.",
    },
    {
        "name": "Day and night cylce",
        "description": "Demonstrates the cycle of day and night on Earth.",
    },
    {
        "name": "Rock and minerals",
        "description": "Provides familiarisation with different types of rocks and mineral samples.",
    },
    {
        "name": "Constellation viewer",
        "description": "Provides a visual activity for identifying and observing constellation patterns.",
    },
    {
        "name": "A*(B+C)=Ab+Ac",
        "description": "Provides a geometrical illustration of the basic algebraic distributive identity.",
    },
    {
        "name": "(A+B)^2=A^2+2ab+B^2",
        "description": "Provides a geometrical illustration of the algebraic identity for the square of a binomial.",
    },
    {
        "name": "(A+B)^-(A-B)^2 = 4ab",
        "description": "Provides a geometrical illustration of an algebraic identity involving the product of binomials.",
    },
    {
        "name": "Area of rhombus",
        "description": "Provides a simple visual illustration of the derivation of the area of a rhombus.",
    },
    {
        "name": "Area of triangle",
        "description": "Provides a simple visual derivation and illustration of the area of a triangle.",
    },
    {
        "name": "Area of parellogram",
        "description": "Provides a simple visual derivation and illustration of the area of a parallelogram.",
    },
    {
        "name": "(A+B)^2 +(A-B)^2= 2a^2+2b^2",
        "description": "Provides a geometrical illustration of an algebraic identity.",
    },
    {
        "name": "(A^2-B^2)=(A+B)(A-B)",
        "description": "Provides a geometrical illustration of the difference of squares identity.",
    },
    {
        "name": "Sum of angles of a quadrilateral",
        "description": "Demonstrates the elementary theorem that the sum of the angles of a quadrilateral is 360 degrees.",
    },
    {
        "name": "Two congruent right triangles",
        "description": "Provides a visual comparison of the areas of different geometric shapes using congruent right triangles.",
    },
    {
        "name": "Area of circle",
        "description": "Provides a simple visual illustration of the derivation of the area of a circle.",
    },
    {
        "name": "Tangram",
        "description": "Provides an engaging puzzle activity for familiarisation with basic geometric shapes.",
    },
    {
        "name": "Pythagorus",
        "description": "Demonstrates the Pythagorean theorem relating the squares of the sides of a right triangle.",
    },
    {
        "name": "Sum of angles of triangle",
        "description": "Demonstrates the elementary theorem that the sum of the angles of a triangle is 180 degrees.",
    },
    {
        "name": "(A+B+C)^2 = A^2 +B^2 + C^2 +2ab+2bc +2ca",
        "description": "Provides a geometrical illustration of a basic algebraic identity involving three terms.",
    },
    {
        "name": "L.C.M",
        "description": "Provides an activity for finding the least common multiple of numbers.",
    },
    {
        "name": "DNA",
        "description": "Demonstrates the double helix structure of DNA and the pairing of A-T and G-C bases.",
    },
    {
        "name": "Blank Paper",
        "description": "Blank paper used by students or the Para-Teacher for drawing, writing, labelling, recording observations or carrying out learning activities.",
    },
    {
        "name": "NA - No TLM Used",
        "description": "Used when no teaching-learning material was used during the session.",
    },
]


def seed_tlm():
    db = SessionLocal()

    try:
        created = 0
        existing = 0

        for tlm_data in TLM_DATA:
            tlm = (
                db.query(TLM)
                .filter(TLM.name == tlm_data["name"])
                .first()
            )

            if tlm:
                existing += 1
                continue

            tlm = TLM(
                name=tlm_data["name"],
                description=tlm_data["description"],
                is_active=True,
                data_origin="PRODUCTION",
            )

            db.add(tlm)
            created += 1

        db.commit()

        print(f"TLM seed complete: {created} created, {existing} already existed.")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_tlm()
