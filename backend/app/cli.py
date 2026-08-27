from pathlib import Path

from app.loaders import load_dataset


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data" / "synthetic"
    dataset = load_dataset(data_dir)

    print("BlockSangam Phase 2 - canonical data load")
    print(f"Engineering tasks : {len(dataset.engineering_tasks)}")
    print(f"S&T tasks         : {len(dataset.snt_tasks)}")
    print(f"TRD tasks         : {len(dataset.trd_tasks)}")
    print(f"Passenger trains  : {len(dataset.passenger_movements)}")
    print(f"Goods movements   : {len(dataset.goods_movements)}")
    print(f"Corridor slots    : {len(dataset.corridor_slots)}")
    print(f"Resources         : {len(dataset.resources)}")
    print(f"Locked commitments: {len(dataset.locked_commitments)}")
    print(f"Adapter errors    : {len(dataset.errors)}")

    if dataset.errors:
        print("\nErrors:")
        for error in dataset.errors:
            print(error)
        raise SystemExit(1)

    print("\nCanonical dataset: VALID")


if __name__ == "__main__":
    main()
